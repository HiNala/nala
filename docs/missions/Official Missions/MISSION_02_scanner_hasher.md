# Mission 02: File Scanner and Content Hasher

## Objective

Build the file system scanner that walks a project directory, discovers all source files, computes SHA-256 content hashes for each file, and stores the results in a SQLite cache. This is the foundation of Nala's incremental indexing system. After this mission, Nala can tell which files have changed since the last scan in milliseconds.

## Why This Matters

Large codebases can have tens of thousands of files. Re-parsing every file on every launch is wasteful. By computing and caching content hashes, Nala only re-indexes files whose content has actually changed. This is the same approach used by Cursor's Merkle-tree indexing and OpenCode's incremental processing. On a 100,000-line codebase, subsequent scans should complete in under 2 seconds because most files will not have changed.

## Context

This work happens entirely in the `nala-indexer` crate. The scanner reads the file system, the hasher computes content hashes, and the cache stores results in SQLite. No parsing or metrics computation happens yet. That comes in Mission 03.

## Implementation Steps

### Step 1: Build the file scanner (scanner.rs)

Create a `Scanner` struct that accepts a root directory path and a set of configuration options:
- `included_extensions`: Which file extensions to scan (e.g., .rs, .py, .ts, .js, .go, .java, .cpp, .c, .rb, .md). Default to a sensible set of common programming language extensions.
- `excluded_dirs`: Which directories to skip (e.g., node_modules, target, .git, __pycache__, .venv, dist, build, .nala). Default to common build/dependency directories.
- `max_file_size`: Skip files larger than this (default 1MB). Huge files are usually generated or vendored.

Use the `walkdir` crate to recursively traverse the directory. For each file that passes the filters, collect its path (relative to root), size in bytes, and last-modified timestamp.

Return a `Vec<ScannedFile>` where `ScannedFile` is a struct containing: relative_path (String), absolute_path (PathBuf), extension (String), size_bytes (u64), modified_at (SystemTime).

### Step 2: Build the content hasher (hasher.rs)

Create a `hash_file(path: &Path) -> Result<String>` function that reads a file's contents and computes a SHA-256 hash, returning it as a hex string. Use the `sha2` crate.

Create a `hash_files(files: &[ScannedFile]) -> Vec<HashedFile>` function that processes files in parallel using Rayon's par_iter. HashedFile extends ScannedFile with a `content_hash: String` field.

Parallelism is important here because hashing is I/O-bound and can benefit from concurrent disk reads on modern SSDs.

### Step 3: Build the SQLite cache (cache.rs)

Create a `Cache` struct that manages a SQLite database stored at `.nala/cache.db` inside the project root.

The database has one table:
```sql
CREATE TABLE IF NOT EXISTS file_index (
    relative_path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    modified_at INTEGER NOT NULL,
    last_indexed_at INTEGER NOT NULL,
    language TEXT,
    symbol_count INTEGER DEFAULT 0
);
```

Implement these methods on Cache:
- `new(project_root: &Path) -> Result<Self>`: Opens or creates the database. Creates the table if it does not exist. Creates the `.nala/` directory if needed.
- `get_hash(path: &str) -> Result<Option<String>>`: Returns the cached hash for a file path.
- `set_hash(path: &str, hash: &str, size: u64, modified: u64) -> Result<()>`: Inserts or updates a file's cache entry.
- `get_changed_files(current_files: &[HashedFile]) -> Result<Vec<HashedFile>>`: Compares the current scan against the cache and returns only files whose hash has changed or that are new.
- `remove_deleted(current_paths: &HashSet<String>) -> Result<u64>`: Removes cache entries for files that no longer exist on disk. Returns count of removed entries.
- `get_all_indexed() -> Result<Vec<CachedFile>>`: Returns all cached file entries.

### Step 4: Build the scan orchestrator (lib.rs additions)

Create a top-level `scan_project(root: &Path) -> Result<ScanResult>` function that:
1. Creates or opens the Cache
2. Runs the Scanner to discover all files
3. Runs the Hasher to compute content hashes
4. Compares hashes against the cache to find changed files
5. Updates the cache with new hashes
6. Removes cache entries for deleted files
7. Returns a ScanResult containing: total_files (usize), changed_files (Vec<HashedFile>), new_files (Vec<HashedFile>), deleted_files (usize), scan_duration (Duration)

### Step 5: Add progress reporting

Create a `ScanProgress` callback trait or closure type that the scanner calls with progress updates: files_discovered, files_hashed, cache_compared. The TUI will use this later to show a progress bar during indexing. For now, just make sure the interface exists.

### Step 6: Write tests

In the nala-indexer crate, create tests that:
- Create a temp directory with some source files
- Run the scanner and verify it discovers the correct files
- Run the hasher and verify hashes are deterministic
- Create a cache, store hashes, modify a file, re-scan, and verify only the modified file appears in the changed set
- Delete a file, re-scan, and verify the deleted file is removed from the cache

### Step 7: Expose via CLI

Update nala-cli/src/main.rs to add a `scan` subcommand that calls `scan_project()` and prints the ScanResult to stdout. This lets us test the scanner from the command line before the TUI exists.

## Acceptance Criteria

- Scanner correctly discovers source files while respecting inclusion/exclusion filters
- Hasher produces deterministic SHA-256 hashes
- Cache correctly identifies new, changed, and deleted files on subsequent scans
- First scan of a 10,000-file directory completes in under 5 seconds
- Subsequent scan (no changes) completes in under 1 second
- All tests pass
- No source file exceeds 400 lines
- `nala scan` CLI command works and prints results

## Key Dependencies

- walkdir (directory traversal)
- sha2 (content hashing)
- rayon (parallel hashing)
- rusqlite (SQLite cache)
- tempfile (for tests)

## Estimated Complexity

Medium. The core logic is straightforward but getting the incremental comparison right (handling renames, moves, deletions) requires careful testing.
