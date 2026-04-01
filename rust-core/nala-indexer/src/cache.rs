//! SQLite-backed index cache.
//!
//! Stores content hashes and symbol metadata for each indexed file.
//! On subsequent runs, only files whose hash has changed are re-parsed —
//! making incremental indexing nearly instant for large, stable codebases.
//!
//! The database lives at `{project_root}/.nala/cache.db`.

use crate::hasher::HashedFile;
use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use std::collections::HashSet;
use std::path::{Path, PathBuf};

// ── Cache entry ────────────────────────────────────────────────────────────

/// A row from the file_index table.
#[derive(Debug, Clone)]
pub struct CachedFile {
    pub relative_path: String,
    pub content_hash: String,
    pub size_bytes: i64,
    pub language: Option<String>,
    pub symbol_count: i64,
    pub last_indexed_at: i64,
}

// ── Cache ──────────────────────────────────────────────────────────────────

/// SQLite cache for incremental indexing.
pub struct Cache {
    conn: Connection,
}

impl Cache {
    /// Open (or create) the cache database at `{root}/.nala/cache.db`.
    pub fn open(root: &Path) -> Result<Self> {
        let nala_dir = root.join(".nala");
        std::fs::create_dir_all(&nala_dir)
            .context("Failed to create .nala directory")?;

        let db_path = nala_dir.join("cache.db");
        let conn = Connection::open(&db_path)
            .with_context(|| format!("Failed to open cache at {}", db_path.display()))?;

        let cache = Self { conn };
        cache.migrate()?;
        Ok(cache)
    }

    /// Return true if a file path has never been indexed before.
    pub fn is_new(&self, relative_path: &str) -> Result<bool> {
        let count: i64 = self.conn.query_row(
            "SELECT COUNT(*) FROM file_index WHERE relative_path = ?1",
            params![relative_path],
            |row| row.get(0),
        )?;
        Ok(count == 0)
    }

    /// Return files from `current` whose hash differs from the cached hash.
    ///
    /// This includes both modified files (hash changed) and new files
    /// (not present in the cache at all).
    pub fn get_changed_files(&self, current: &[HashedFile]) -> Result<Vec<HashedFile>> {
        let mut changed = Vec::new();
        for file in current {
            let cached_hash: Option<String> = self
                .conn
                .query_row(
                    "SELECT content_hash FROM file_index WHERE relative_path = ?1",
                    params![file.relative_path],
                    |row| row.get(0),
                )
                .optional()?;

            match cached_hash {
                None => changed.push(file.clone()),                    // new file
                Some(h) if h != file.content_hash => changed.push(file.clone()), // changed
                _ => {}                                                 // unchanged
            }
        }
        Ok(changed)
    }

    /// Insert or update hash entries for the given files.
    pub fn update_hashes(&mut self, files: &[HashedFile]) -> Result<()> {
        let tx = self.conn.transaction()?;
        let now = now_unix();
        for file in files {
            tx.execute(
                "INSERT INTO file_index (relative_path, content_hash, size_bytes, last_indexed_at)
                 VALUES (?1, ?2, ?3, ?4)
                 ON CONFLICT(relative_path) DO UPDATE SET
                     content_hash     = excluded.content_hash,
                     size_bytes       = excluded.size_bytes,
                     last_indexed_at  = excluded.last_indexed_at",
                params![file.relative_path, file.content_hash, file.size_bytes as i64, now],
            )?;
        }
        tx.commit()?;
        Ok(())
    }

    /// Remove cache entries for files that no longer exist on disk.
    ///
    /// Returns the number of entries removed.
    pub fn remove_deleted_files(&mut self, current: &[HashedFile]) -> Result<usize> {
        let current_paths: HashSet<&str> =
            current.iter().map(|f| f.relative_path.as_str()).collect();

        let all_paths: Vec<String> = {
            let mut stmt = self.conn.prepare("SELECT relative_path FROM file_index")?;
            let rows: Vec<String> = stmt
                .query_map([], |row| row.get(0))?
                .filter_map(|r| r.ok())
                .collect();
            rows
        };

        let mut removed = 0;
        for path in &all_paths {
            if !current_paths.contains(path.as_str()) {
                self.conn.execute(
                    "DELETE FROM file_index WHERE relative_path = ?1",
                    params![path],
                )?;
                removed += 1;
            }
        }
        Ok(removed)
    }

    /// Update the symbol count and language for a file after parsing.
    pub fn update_symbol_metadata(
        &mut self,
        relative_path: &str,
        language: &str,
        symbol_count: usize,
    ) -> Result<()> {
        self.conn.execute(
            "UPDATE file_index SET language = ?1, symbol_count = ?2 WHERE relative_path = ?3",
            params![language, symbol_count as i64, relative_path],
        )?;
        Ok(())
    }

    /// Return all cached file entries.
    pub fn get_all(&self) -> Result<Vec<CachedFile>> {
        let mut stmt = self.conn.prepare(
            "SELECT relative_path, content_hash, size_bytes, language, symbol_count, last_indexed_at
             FROM file_index",
        )?;
        let rows = stmt
            .query_map([], |row| {
                Ok(CachedFile {
                    relative_path: row.get(0)?,
                    content_hash: row.get(1)?,
                    size_bytes: row.get(2)?,
                    language: row.get(3)?,
                    symbol_count: row.get(4)?,
                    last_indexed_at: row.get(5)?,
                })
            })?
            .filter_map(|r| r.ok())
            .collect();
        Ok(rows)
    }

    // ── Private ────────────────────────────────────────────────────────────

    fn migrate(&self) -> Result<()> {
        self.conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA synchronous=NORMAL;
             CREATE TABLE IF NOT EXISTS file_index (
                 relative_path    TEXT PRIMARY KEY,
                 content_hash     TEXT NOT NULL,
                 size_bytes       INTEGER NOT NULL DEFAULT 0,
                 last_indexed_at  INTEGER NOT NULL DEFAULT 0,
                 language         TEXT,
                 symbol_count     INTEGER NOT NULL DEFAULT 0
             );
             CREATE INDEX IF NOT EXISTS idx_file_index_hash
                 ON file_index (content_hash);",
        )?;
        Ok(())
    }
}

// ── Helpers ────────────────────────────────────────────────────────────────

fn now_unix() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

// rusqlite optional() helper
trait OptionalExt<T> {
    fn optional(self) -> Result<Option<T>>;
}

impl<T> OptionalExt<T> for rusqlite::Result<T> {
    fn optional(self) -> Result<Option<T>> {
        match self {
            Ok(v) => Ok(Some(v)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }
}

// ── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use tempfile::TempDir;

    fn make_hashed(path: &str, hash: &str) -> HashedFile {
        HashedFile {
            relative_path: path.to_string(),
            absolute_path: PathBuf::from(path),
            extension: "rs".to_string(),
            size_bytes: 100,
            content_hash: hash.to_string(),
        }
    }

    #[test]
    fn new_files_are_detected_as_changed() {
        let dir = tempfile::tempdir().unwrap();
        let mut cache = Cache::open(dir.path()).unwrap();
        let files = vec![make_hashed("src/main.rs", "abc123")];
        let changed = cache.get_changed_files(&files).unwrap();
        assert_eq!(changed.len(), 1);
    }

    #[test]
    fn unchanged_files_are_not_in_changed_set() {
        let dir = tempfile::tempdir().unwrap();
        let mut cache = Cache::open(dir.path()).unwrap();
        let files = vec![make_hashed("src/main.rs", "abc123")];
        cache.update_hashes(&files).unwrap();
        let changed = cache.get_changed_files(&files).unwrap();
        assert_eq!(changed.len(), 0);
    }

    #[test]
    fn modified_file_appears_in_changed_set() {
        let dir = tempfile::tempdir().unwrap();
        let mut cache = Cache::open(dir.path()).unwrap();
        let original = vec![make_hashed("src/main.rs", "abc123")];
        cache.update_hashes(&original).unwrap();
        let modified = vec![make_hashed("src/main.rs", "xyz999")];
        let changed = cache.get_changed_files(&modified).unwrap();
        assert_eq!(changed.len(), 1);
    }
}
