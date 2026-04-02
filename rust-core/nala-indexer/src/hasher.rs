//! Content hasher.
//!
//! Reads each scanned file and computes a SHA-256 content hash.
//! Uses Rayon to process files in parallel across CPU cores — hashing is
//! I/O-bound and benefits heavily from concurrent reads on modern SSDs.

use crate::scanner::ScannedFile;
use anyhow::Result;
use rayon::prelude::*;
use sha2::{Digest, Sha256};
use std::fs;

// ── Hashed file ────────────────────────────────────────────────────────────

/// A scanned file with its content hash computed.
#[derive(Debug, Clone)]
pub struct HashedFile {
    pub relative_path: String,
    pub absolute_path: std::path::PathBuf,
    pub extension: String,
    pub size_bytes: u64,
    pub content_hash: String,
}

impl From<(ScannedFile, String)> for HashedFile {
    fn from((file, hash): (ScannedFile, String)) -> Self {
        Self {
            relative_path: file.relative_path,
            absolute_path: file.absolute_path,
            extension: file.extension,
            size_bytes: file.size_bytes,
            content_hash: hash,
        }
    }
}

// ── Public API ─────────────────────────────────────────────────────────────

/// Compute SHA-256 hashes for a slice of scanned files in parallel.
///
/// Files that cannot be read are logged as warnings and skipped.
pub fn hash_files(files: &[ScannedFile]) -> Vec<HashedFile> {
    files
        .par_iter()
        .filter_map(|file| {
            match hash_file_content(&file.absolute_path) {
                Ok(hash) => Some(HashedFile::from((file.clone(), hash))),
                Err(e) => {
                    tracing::warn!("Failed to hash {}: {}", file.relative_path, e);
                    None
                }
            }
        })
        .collect()
}

/// Compute the SHA-256 hash of a single file's content.
///
/// Returns the hash as a 64-character lowercase hex string.
pub fn hash_file_content(path: &std::path::Path) -> Result<String> {
    let content = fs::read(path)?;
    let mut hasher = Sha256::new();
    hasher.update(&content);
    let result = hasher.finalize();
    Ok(format!("{:x}", result))
}

// ── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn temp_file(dir: &TempDir, name: &str, content: &str) -> ScannedFile {
        let path = dir.path().join(name);
        fs::write(&path, content).unwrap();
        ScannedFile {
            relative_path: name.to_string(),
            absolute_path: path,
            extension: name.rsplit('.').next().unwrap_or("").to_string(),
            size_bytes: content.len() as u64,
            modified_at: std::time::SystemTime::now(),
        }
    }

    #[test]
    fn hash_is_deterministic() {
        let dir = tempfile::tempdir().unwrap();
        let file = temp_file(&dir, "test.rs", "fn main() {}");
        let h1 = hash_file_content(&file.absolute_path).unwrap();
        let h2 = hash_file_content(&file.absolute_path).unwrap();
        assert_eq!(h1, h2);
    }

    #[test]
    fn different_content_produces_different_hash() {
        let dir = tempfile::tempdir().unwrap();
        let f1 = temp_file(&dir, "a.rs", "fn main() {}");
        let f2 = temp_file(&dir, "b.rs", "fn other() {}");
        let h1 = hash_file_content(&f1.absolute_path).unwrap();
        let h2 = hash_file_content(&f2.absolute_path).unwrap();
        assert_ne!(h1, h2);
    }

    #[test]
    fn hash_files_processes_in_parallel() {
        let dir = tempfile::tempdir().unwrap();
        let files: Vec<_> = (0..10)
            .map(|i| temp_file(&dir, &format!("file{i}.rs"), &format!("fn f{i}() {{}}")))
            .collect();
        let hashed = hash_files(&files);
        assert_eq!(hashed.len(), 10);
    }
}
