//! nala-indexer: file scanning, content hashing, Tree-sitter parsing, and code metrics.
//!
//! Public API surface:
//!
//! - `scan_project(root)` — fast file discovery + content hash comparison
//! - `index_project(root)` — full scan + parse + symbol extraction + metrics
//!
//! Both functions are designed to be called from the TUI, the CLI, and the PyO3 bridge.

pub mod cache;
pub mod hasher;
pub mod metrics;
pub mod parser;
pub mod scanner;
pub mod symbol_graph;

use anyhow::Result;
use std::path::Path;
use std::time::Duration;

pub use cache::Cache;
pub use hasher::HashedFile;
pub use parser::ParsedFile;
pub use scanner::ScannedFile;
pub use symbol_graph::Symbol;

// ── Top-level result types ─────────────────────────────────────────────────

/// Result of a file-system scan (no parsing yet).
#[derive(Debug)]
pub struct ScanResult {
    pub total_files: usize,
    pub changed_files: Vec<HashedFile>,
    pub new_files: Vec<HashedFile>,
    pub deleted_count: usize,
    pub scan_duration: Duration,
}

/// Result of a full index pass (scan + parse + symbols + metrics).
#[derive(Debug)]
pub struct IndexResult {
    pub scan_result: ScanResult,
    pub indexed_files: usize,
    pub total_symbols: usize,
    pub function_count: usize,
    pub class_count: usize,
    pub import_count: usize,
    pub index_duration: Duration,
    /// All extracted symbols (empty when nothing changed).
    pub symbols: Vec<Symbol>,
}

// ── Public API ─────────────────────────────────────────────────────────────

/// Scan a project directory: discover files, compute hashes, compare to cache.
///
/// This is the fast path. On projects with thousands of unchanged files it
/// completes in milliseconds because it only reads file metadata and compares
/// hashes.
pub fn scan_project(root: &Path) -> Result<ScanResult> {
    let start = std::time::Instant::now();

    let config = scanner::ScanConfig::default();
    let scanned = scanner::Scanner::new(root, config).scan()?;
    let hashed = hasher::hash_files(&scanned);

    let mut cache = Cache::open(root)?;
    let changed = cache.get_changed_files(&hashed)?;
    let new_files: Vec<_> = changed
        .iter()
        .filter(|f| cache.is_new(&f.relative_path).unwrap_or(false))
        .cloned()
        .collect();
    let deleted = cache.remove_deleted_files(&hashed)?;

    cache.update_hashes(&hashed)?;

    Ok(ScanResult {
        total_files: hashed.len(),
        changed_files: changed,
        new_files,
        deleted_count: deleted,
        scan_duration: start.elapsed(),
    })
}

/// Index a project: scan, then parse changed files and extract symbols/metrics.
///
/// On subsequent runs, only re-parses files whose content hash has changed.
/// Uses Rayon for parallel parsing across CPU cores.
pub fn index_project(root: &Path) -> Result<IndexResult> {
    let start = std::time::Instant::now();
    let scan_result = scan_project(root)?;

    let files_to_parse = if scan_result.changed_files.is_empty() {
        // Nothing changed — load symbols from cache
        tracing::debug!("No files changed, skipping parse");
        return Ok(IndexResult {
            indexed_files: 0,
            total_symbols: 0,
            function_count: 0,
            class_count: 0,
            import_count: 0,
            index_duration: start.elapsed(),
            symbols: Vec::new(),
            scan_result,
        });
    } else {
        scan_result.changed_files.clone()
    };

    let symbols = parser::parse_files_parallel(&files_to_parse, root)?;

    let function_count = symbols.iter().filter(|s| s.kind == symbol_graph::SymbolKind::Function).count();
    let class_count = symbols.iter().filter(|s| s.kind == symbol_graph::SymbolKind::Class).count();
    let import_count = symbols.iter().filter(|s| s.kind == symbol_graph::SymbolKind::Import).count();
    let total_symbols = symbols.len();
    let indexed_files = files_to_parse.len();

    Ok(IndexResult {
        scan_result,
        indexed_files,
        total_symbols,
        function_count,
        class_count,
        import_count,
        index_duration: start.elapsed(),
        symbols,
    })
}
