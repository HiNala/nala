# Mission 02: File Scanner and Content Hasher

## Objective

Build the file system scanner that walks a project directory, discovers source files, computes SHA-256 content hashes, and stores results in a SQLite cache. This is the foundation of Nala's incremental indexing — on subsequent launches, only re-index changed files.

## Why This Matters

Large codebases can have tens of thousands of files. Re-parsing everything on every launch is wasteful. By computing and caching content hashes (same approach Cursor uses with Merkle-tree indexing and OpenCode uses for incremental processing), subsequent scans on a 100k-line project complete in under 2 seconds because most files haven't changed.

## Context

All work is in `nala-indexer`. The scanner reads the file system, the hasher computes SHA-256 hashes, and the cache stores results in `{project}/.nala/cache.db`. No parsing or metrics happen yet — that's Mission 03.

## Status

**Already implemented in the foundation.** See:
- `rust-core/nala-indexer/src/scanner.rs` — file walker with inclusion/exclusion filters
- `rust-core/nala-indexer/src/hasher.rs` — parallel SHA-256 hashing with Rayon
- `rust-core/nala-indexer/src/cache.rs` — SQLite cache with incremental change detection
- `rust-core/nala-indexer/src/lib.rs` — `scan_project()` orchestrator

## Acceptance Criteria

- [ ] Scanner correctly discovers source files while respecting inclusion/exclusion filters
- [ ] Hasher produces deterministic SHA-256 hashes
- [ ] Cache correctly identifies new, changed, and deleted files
- [ ] First scan of 10,000 files completes in under 5 seconds
- [ ] Subsequent scan (no changes) completes in under 1 second
- [ ] All tests pass (`cargo test -p nala-indexer`)
- [ ] `nala scan` CLI command works and prints results

## Extension Points for Mission 03

`scan_project()` returns `ScanResult.changed_files` — Mission 03's `index_project()` passes these directly to the Tree-sitter parser. No structural changes needed.
