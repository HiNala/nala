//! LSP client manager.
//!
//! Manages the lifecycle of a language server process for a project and
//! provides async methods for the most common LSP operations:
//!
//!   - `initialize()`         — start the server and run the init handshake
//!   - `go_to_definition()`   — textDocument/definition
//!   - `find_references()`    — textDocument/references
//!   - `hover()`              — textDocument/hover
//!   - `shutdown()`           — graceful server shutdown
//!
//! If no suitable language server is installed, all methods return `Ok(None)`
//! or `Ok(vec![])` without crashing. Nala degrades gracefully.

use crate::config::{detect_server, LspServer};
use crate::diagnostics::DiagnosticsStore;
use crate::transport::{LspTransport, NotificationCallback};
use anyhow::Result;
use serde_json::json;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use url::Url;

// ── Public return types ───────────────────────────────────────────────────────

/// Result of a go-to-definition query.
#[derive(Debug, Clone)]
pub struct DefinitionLocation {
    pub file_path:  PathBuf,
    pub start_line: usize,
    pub start_col:  usize,
}

/// A reference found by find-references.
#[derive(Debug, Clone)]
pub struct Reference {
    pub file_path: PathBuf,
    pub line:      usize,
    pub col:       usize,
}

/// Hover information for a symbol.
#[derive(Debug, Clone)]
pub struct HoverInfo {
    pub contents: String,
}

// ── LspManager ────────────────────────────────────────────────────────────────

/// Manages one LSP server connection for a project.
pub struct LspManager {
    project_root: PathBuf,
    server:       LspServer,
    transport:    Option<LspTransport>,
    initialized:  bool,
    diagnostics:  DiagnosticsStore,
}

impl LspManager {
    /// Create a new manager for the given project root.
    /// Auto-detects the appropriate language server.
    pub fn new(project_root: &Path) -> Self {
        Self::with_diagnostics_store(project_root, DiagnosticsStore::new())
    }

    /// Create a manager sharing an external diagnostics store (for TUI integration).
    pub fn with_diagnostics_store(project_root: &Path, diagnostics: DiagnosticsStore) -> Self {
        let server = detect_server(project_root);
        tracing::debug!("LSP server detected: {}", server);
        Self {
            project_root: project_root.to_path_buf(),
            server,
            transport: None,
            initialized: false,
            diagnostics,
        }
    }

    /// Whether the server has completed the initialize handshake.
    pub fn is_initialized(&self) -> bool {
        self.initialized
    }

    /// Access the live diagnostics store (updated by the LSP server in the background).
    pub fn diagnostics(&self) -> &DiagnosticsStore {
        &self.diagnostics
    }

    /// Return the detected language server type.
    pub fn server(&self) -> &LspServer {
        &self.server
    }

    /// Start the LSP server process and perform the initialize handshake.
    pub async fn initialize(&mut self) -> Result<()> {
        if self.server == LspServer::None {
            tracing::debug!("No LSP server available for this project");
            return Ok(());
        }
        if self.initialized {
            return Ok(());
        }

        let (cmd, args) = self.server.command_and_args();
        tracing::info!("Starting LSP server: {} {:?}", cmd, args);

        let diag_store = self.diagnostics.clone();
        let on_notification: NotificationCallback = Arc::new(move |method, params| {
            if method == "textDocument/publishDiagnostics" {
                diag_store.handle_publish_diagnostics(&params);
            }
        });

        let arg_refs: Vec<&str> = args.iter().map(String::as_str).collect();
        let transport = match LspTransport::spawn_with_notifications(
            &cmd,
            &arg_refs,
            &self.project_root,
            Some(on_notification),
        )
        .await
        {
            Ok(t) => t,
            Err(e) => {
                tracing::warn!(
                    "LSP server '{}' failed to start: {e} — degrading gracefully",
                    cmd
                );
                return Ok(());
            }
        };

        let root_uri = path_to_uri(&self.project_root);
        let init_result = transport
            .request(
                "initialize",
                json!({
                    "processId": std::process::id(),
                    "rootUri": root_uri,
                    "capabilities": {
                        "textDocument": {
                            "definition":  { "dynamicRegistration": false },
                            "references":  { "dynamicRegistration": false },
                            "hover": {
                                "dynamicRegistration": false,
                                "contentFormat": ["plaintext", "markdown"],
                            },
                            "publishDiagnostics": {
                                "relatedInformation": true,
                            },
                        },
                        "workspace": {
                            "workspaceFolders": true,
                        },
                    },
                    "workspaceFolders": [{"uri": root_uri, "name": "root"}],
                }),
            )
            .await;

        match init_result {
            Ok(_) => {
                transport.notify("initialized", json!({})).await?;
                self.transport = Some(transport);
                self.initialized = true;
                tracing::info!("LSP server initialized: {}", self.server);
            }
            Err(e) => {
                tracing::warn!("LSP initialize handshake failed: {e}");
            }
        }

        Ok(())
    }

    /// Find the definition of the symbol at the given file/line/col.
    pub async fn go_to_definition(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Option<DefinitionLocation>> {
        let transport = match &self.transport {
            Some(t) => t,
            None => return Ok(None),
        };

        let resp = transport.request(
            "textDocument/definition",
            json!({
                "textDocument": { "uri": path_to_uri(file) },
                "position": { "line": line, "character": col },
            }),
        ).await?;

        // Response is Location | Location[] | LocationLink[] | null
        let loc = if resp["result"].is_array() {
            resp["result"].as_array().and_then(|arr| arr.first()).cloned()
        } else if resp["result"].is_object() {
            Some(resp["result"].clone())
        } else {
            None
        };

        if let Some(loc) = loc {
            if let (Some(uri), Some(range)) = (
                loc["uri"].as_str(),
                loc.get("range").or_else(|| loc.get("targetRange")),
            ) {
                let file_path = uri_to_path(uri);
                let start_line = range["start"]["line"].as_u64().unwrap_or(0) as usize;
                let start_col  = range["start"]["character"].as_u64().unwrap_or(0) as usize;
                return Ok(Some(DefinitionLocation { file_path, start_line, start_col }));
            }
        }

        Ok(None)
    }

    /// Find all references to the symbol at the given file/line/col.
    pub async fn find_references(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Vec<Reference>> {
        let transport = match &self.transport {
            Some(t) => t,
            None => return Ok(vec![]),
        };

        let resp = transport.request(
            "textDocument/references",
            json!({
                "textDocument": { "uri": path_to_uri(file) },
                "position": { "line": line, "character": col },
                "context": { "includeDeclaration": true },
            }),
        ).await?;

        let mut refs = Vec::new();
        if let Some(arr) = resp["result"].as_array() {
            for loc in arr {
                if let (Some(uri), Some(range)) = (loc["uri"].as_str(), loc.get("range")) {
                    refs.push(Reference {
                        file_path: uri_to_path(uri),
                        line: range["start"]["line"].as_u64().unwrap_or(0) as usize,
                        col:  range["start"]["character"].as_u64().unwrap_or(0) as usize,
                    });
                }
            }
        }

        Ok(refs)
    }

    /// Get hover documentation for the symbol at the given file/line/col.
    pub async fn hover(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Option<HoverInfo>> {
        let transport = match &self.transport {
            Some(t) => t,
            None => return Ok(None),
        };

        let resp = transport.request(
            "textDocument/hover",
            json!({
                "textDocument": { "uri": path_to_uri(file) },
                "position": { "line": line, "character": col },
            }),
        ).await?;

        let contents = match resp["result"].get("contents") {
            Some(c) if c.is_string() => c.as_str().unwrap_or("").to_string(),
            Some(c) if c.is_object() => {
                c["value"].as_str().unwrap_or("").to_string()
            }
            Some(c) if c.is_array() => {
                c.as_array()
                    .unwrap_or(&vec![])
                    .iter()
                    .filter_map(|v| {
                        if v.is_string() {
                            v.as_str().map(str::to_string)
                        } else {
                            v["value"].as_str().map(str::to_string)
                        }
                    })
                    .collect::<Vec<_>>()
                    .join("\n\n")
            }
            _ => return Ok(None),
        };

        if contents.is_empty() {
            Ok(None)
        } else {
            Ok(Some(HoverInfo { contents }))
        }
    }

    /// Shut down the LSP server gracefully.
    pub async fn shutdown(&self) -> Result<()> {
        if let Some(transport) = &self.transport {
            let _ = transport.request("shutdown", serde_json::Value::Null).await;
            let _ = transport.notify("exit", serde_json::Value::Null).await;
            tracing::info!("LSP server shut down: {}", self.server);
        }
        Ok(())
    }
}

// ── URI helpers ───────────────────────────────────────────────────────────────

fn path_to_uri(path: &Path) -> String {
    // Best-effort: canonicalize if possible, then convert.
    let canonical = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    // On Windows, Url::from_file_path handles drive letters correctly.
    Url::from_file_path(&canonical)
        .map(|u| u.to_string())
        .unwrap_or_else(|_| format!("file:///{}", canonical.display()))
}

pub(crate) fn uri_to_path(uri: &str) -> PathBuf {
    Url::parse(uri)
        .ok()
        .and_then(|u| u.to_file_path().ok())
        .unwrap_or_else(|| {
            // Fallback: strip "file://" prefix.
            let stripped = uri.strip_prefix("file://").unwrap_or(uri);
            PathBuf::from(stripped)
        })
}
