//! Diagnostics store for LSP `textDocument/publishDiagnostics` notifications.
//!
//! The LSP server pushes diagnostics as JSON-RPC notifications. This module
//! parses them into a typed structure and maintains a per-file cache that
//! the TUI can query cheaply.

use serde_json::Value;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, RwLock};

/// A single diagnostic entry (error, warning, hint).
#[derive(Debug, Clone)]
pub struct Diagnostic {
    pub file: PathBuf,
    pub line: usize,
    pub col: usize,
    pub severity: DiagSeverity,
    pub message: String,
    pub source: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiagSeverity {
    Error,
    Warning,
    Info,
    Hint,
}

impl DiagSeverity {
    fn from_lsp(n: u64) -> Self {
        match n {
            1 => Self::Error,
            2 => Self::Warning,
            3 => Self::Info,
            _ => Self::Hint,
        }
    }
}

/// Thread-safe diagnostics cache keyed by file path.
#[derive(Debug, Clone, Default)]
pub struct DiagnosticsStore {
    inner: Arc<RwLock<HashMap<PathBuf, Vec<Diagnostic>>>>,
}

impl DiagnosticsStore {
    pub fn new() -> Self {
        Self::default()
    }

    /// Replace diagnostics for a file (called on each publishDiagnostics notification).
    pub fn update(&self, file: PathBuf, diags: Vec<Diagnostic>) {
        if let Ok(mut map) = self.inner.write() {
            if diags.is_empty() {
                map.remove(&file);
            } else {
                map.insert(file, diags);
            }
        }
    }

    /// Total number of errors across all files.
    pub fn error_count(&self) -> usize {
        self.inner
            .read()
            .map(|m| {
                m.values()
                    .flat_map(|v| v.iter())
                    .filter(|d| d.severity == DiagSeverity::Error)
                    .count()
            })
            .unwrap_or(0)
    }

    /// Total number of warnings across all files.
    pub fn warning_count(&self) -> usize {
        self.inner
            .read()
            .map(|m| {
                m.values()
                    .flat_map(|v| v.iter())
                    .filter(|d| d.severity == DiagSeverity::Warning)
                    .count()
            })
            .unwrap_or(0)
    }

    /// Get diagnostics for a specific file.
    pub fn for_file(&self, file: &PathBuf) -> Vec<Diagnostic> {
        self.inner
            .read()
            .map(|m| m.get(file).cloned().unwrap_or_default())
            .unwrap_or_default()
    }

    /// Return a snapshot of the full diagnostics map (for display in the TUI).
    pub fn inner_snapshot(&self) -> Result<HashMap<PathBuf, Vec<Diagnostic>>, ()> {
        self.inner.read().map(|m| m.clone()).map_err(|_| ())
    }

    /// Parse a `textDocument/publishDiagnostics` params object and update the store.
    pub fn handle_publish_diagnostics(&self, params: &Value) {
        let uri = match params.get("uri").and_then(|v| v.as_str()) {
            Some(u) => u,
            None => return,
        };
        let file = crate::client::uri_to_path(uri);

        let diags = params
            .get("diagnostics")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|d| {
                        let range = d.get("range")?;
                        let start = range.get("start")?;
                        let line = start.get("line")?.as_u64()? as usize;
                        let col = start.get("character")?.as_u64()? as usize;
                        let severity =
                            DiagSeverity::from_lsp(d.get("severity")?.as_u64().unwrap_or(4));
                        let message = d
                            .get("message")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        let source = d
                            .get("source")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        Some(Diagnostic {
                            file: file.clone(),
                            line,
                            col,
                            severity,
                            message,
                            source,
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();

        self.update(file, diags);
    }
}
