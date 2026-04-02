//! File system scanner.
//!
//! Walks a project directory recursively and returns a list of source files
//! that pass the inclusion/exclusion filters. Does not read file contents —
//! that is the hasher's job.

use anyhow::Result;
use std::path::{Path, PathBuf};
use std::time::SystemTime;
use walkdir::WalkDir;

// ── Configuration ──────────────────────────────────────────────────────────

/// Configuration for the file scanner.
#[derive(Debug, Clone)]
pub struct ScanConfig {
    /// File extensions to include (without the leading dot).
    pub included_extensions: Vec<String>,
    /// Directory names to skip entirely.
    pub excluded_dirs: Vec<String>,
    /// Skip files larger than this many bytes (default: 1 MB).
    pub max_file_size: u64,
}

impl Default for ScanConfig {
    fn default() -> Self {
        Self {
            included_extensions: vec![
                "rs", "py", "js", "jsx", "ts", "tsx", "go", "java", "c", "cpp", "cc",
                "h", "hpp", "rb", "php", "swift", "kt", "scala", "cs", "fs", "ml",
                "ex", "exs", "hs", "lua", "r", "jl", "dart", "toml", "yaml", "yml",
                "json", "md", "sh", "bash", "zsh",
            ]
            .into_iter()
            .map(String::from)
            .collect(),

            excluded_dirs: vec![
                "target", "node_modules", ".git", "__pycache__", ".venv", "venv",
                "dist", "build", ".nala", ".next", ".nuxt", "coverage", ".pytest_cache",
                ".mypy_cache", ".ruff_cache", "vendor", "Pods", ".gradle",
            ]
            .into_iter()
            .map(String::from)
            .collect(),

            max_file_size: 1024 * 1024, // 1 MB
        }
    }
}

// ── Scanned file ───────────────────────────────────────────────────────────

/// A file discovered by the scanner, before content hashing.
#[derive(Debug, Clone)]
pub struct ScannedFile {
    /// Path relative to the project root.
    pub relative_path: String,
    /// Absolute path on the file system.
    pub absolute_path: PathBuf,
    /// File extension (without dot), e.g. "rs".
    pub extension: String,
    /// File size in bytes.
    pub size_bytes: u64,
    /// Last modification time.
    pub modified_at: SystemTime,
}

// ── Scanner ────────────────────────────────────────────────────────────────

/// Recursively walks a project directory and collects matching source files.
pub struct Scanner {
    root: PathBuf,
    config: ScanConfig,
}

impl Scanner {
    pub fn new(root: &Path, config: ScanConfig) -> Self {
        Self {
            root: root.to_path_buf(),
            config,
        }
    }

    /// Walk the directory tree and return all matching files.
    pub fn scan(&self) -> Result<Vec<ScannedFile>> {
        let mut files = Vec::new();

        let walker = WalkDir::new(&self.root)
            .follow_links(false)
            .into_iter()
            .filter_entry(|entry| self.should_visit(entry));

        for entry in walker {
            let entry = entry?;
            if !entry.file_type().is_file() {
                continue;
            }

            let metadata = entry.metadata()?;
            if metadata.len() > self.config.max_file_size {
                continue;
            }

            let ext = entry
                .path()
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("")
                .to_lowercase();

            if !self.config.included_extensions.contains(&ext) {
                continue;
            }

            let relative = entry
                .path()
                .strip_prefix(&self.root)
                .map(|p| p.to_string_lossy().replace('\\', "/"))
                .unwrap_or_default();

            files.push(ScannedFile {
                relative_path: relative,
                absolute_path: entry.path().to_path_buf(),
                extension: ext,
                size_bytes: metadata.len(),
                modified_at: metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH),
            });
        }

        tracing::debug!("Scanner found {} files in {}", files.len(), self.root.display());
        Ok(files)
    }

    /// Returns true if a directory entry should be visited.
    fn should_visit(&self, entry: &walkdir::DirEntry) -> bool {
        if entry.file_type().is_dir() {
            // The root entry can be "." for relative scans. Never treat it as hidden.
            if entry.depth() == 0 {
                return true;
            }
            let name = entry.file_name().to_string_lossy();
            // Skip excluded directories (including hidden dirs except .github)
            if self.config.excluded_dirs.contains(&name.to_string()) {
                return false;
            }
            if name.starts_with('.') && name != ".github" {
                return false;
            }
        }
        true
    }
}

// ── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn make_temp_project() -> TempDir {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("main.rs"), "fn main() {}").unwrap();
        fs::write(dir.path().join("lib.py"), "def hello(): pass").unwrap();
        fs::create_dir(dir.path().join("node_modules")).unwrap();
        fs::write(dir.path().join("node_modules").join("index.js"), "").unwrap();
        dir
    }

    #[test]
    fn scanner_finds_source_files() {
        let dir = make_temp_project();
        let scanner = Scanner::new(dir.path(), ScanConfig::default());
        let files = scanner.scan().unwrap();
        assert_eq!(files.len(), 2);
    }

    #[test]
    fn scanner_excludes_node_modules() {
        let dir = make_temp_project();
        let scanner = Scanner::new(dir.path(), ScanConfig::default());
        let files = scanner.scan().unwrap();
        assert!(!files.iter().any(|f| f.relative_path.contains("node_modules")));
    }
}
