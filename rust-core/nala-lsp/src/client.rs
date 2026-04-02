//! LSP client manager.
//!
//! Manages the lifecycle of a language server process for a project and
//! provides async methods for the most common LSP operations:
//!
//!   - `initialize()`         -- start the server and run the init handshake
//!   - `did_open()`           -- notify the server a document is open
//!   - `go_to_definition()`   -- textDocument/definition
//!   - `find_references()`    -- textDocument/references
//!   - `hover()`              -- textDocument/hover
//!   - `shutdown()`           -- graceful server shutdown
//!
//! If no suitable language server is installed, all methods return `Ok(None)`
//! or `Ok(vec![])` without crashing. Nala degrades gracefully.

use crate::config::{detect_server, LspServer};
use crate::diagnostics::DiagnosticsStore;
use crate::transport::{LspTransport, NotificationCallback};
use anyhow::Result;
use serde_json::json;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::sync::Mutex;
use url::Url;

#[derive(Debug, Clone)]
pub struct DefinitionLocation {
    pub file_path: PathBuf,
    pub start_line: usize,
    pub start_col: usize,
}

#[derive(Debug, Clone)]
pub struct Reference {
    pub file_path: PathBuf,
    pub line: usize,
    pub col: usize,
}

#[derive(Debug, Clone)]
pub struct HoverInfo {
    pub contents: String,
}

/// Shared handle to a persistent LSP connection. Cheap to clone.
#[derive(Clone)]
pub struct LspHandle {
    inner: Arc<Mutex<LspManagerInner>>,
}

struct LspManagerInner {
    project_root: PathBuf,
    server: LspServer,
    transport: Option<LspTransport>,
    initialized: bool,
    opened_files: HashMap<PathBuf, OpenDocumentState>,
    diagnostics: DiagnosticsStore,
}

struct OpenDocumentState {
    version: i32,
    text: String,
}

impl LspHandle {
    pub fn new(project_root: &Path, diagnostics: DiagnosticsStore) -> Self {
        let server = detect_server(project_root);
        tracing::debug!("LSP server detected: {}", server);
        Self {
            inner: Arc::new(Mutex::new(LspManagerInner {
                project_root: project_root.to_path_buf(),
                server,
                transport: None,
                initialized: false,
                opened_files: HashMap::new(),
                diagnostics,
            })),
        }
    }

    pub async fn server_name(&self) -> String {
        self.inner.lock().await.server.to_string()
    }

    pub async fn is_initialized(&self) -> bool {
        self.inner.lock().await.initialized
    }

    pub async fn diagnostics(&self) -> DiagnosticsStore {
        self.inner.lock().await.diagnostics.clone()
    }

    pub async fn initialize(&self) -> Result<()> {
        let mut inner = self.inner.lock().await;
        if inner.server == LspServer::None {
            tracing::debug!("No LSP server available for this project");
            return Ok(());
        }
        if inner.initialized {
            return Ok(());
        }

        let (cmd, args) = inner.server.command_and_args();
        tracing::info!("Starting LSP server: {} {:?}", cmd, args);

        let diag_store = inner.diagnostics.clone();
        let on_notification: NotificationCallback = Arc::new(move |method, params| {
            if method == "textDocument/publishDiagnostics" {
                diag_store.handle_publish_diagnostics(&params);
            }
        });

        let arg_refs: Vec<&str> = args.iter().map(String::as_str).collect();
        let transport = match LspTransport::spawn_with_notifications(
            &cmd,
            &arg_refs,
            &inner.project_root,
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

        let root_uri = path_to_uri(&inner.project_root);
        let init_result = transport
            .request(
                "initialize",
                json!({
                    "processId": std::process::id(),
                    "rootUri": root_uri,
                    "capabilities": {
                        "textDocument": {
                            "synchronization": {
                                "openClose": true,
                                "change": 1,
                            },
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
                inner.transport = Some(transport);
                inner.initialized = true;
                tracing::info!("LSP server initialized: {}", inner.server);
            }
            Err(e) => {
                tracing::warn!("LSP initialize handshake failed: {e}");
            }
        }

        Ok(())
    }

    async fn ensure_file_open(&self, file: &Path) -> Result<()> {
        let canonical = file.canonicalize().unwrap_or_else(|_| file.to_path_buf());
        let text = tokio::fs::read_to_string(&canonical)
            .await
            .unwrap_or_default();
        let lang_id = detect_language_id(&canonical);
        let uri = path_to_uri(&canonical);

        let mut inner = self.inner.lock().await;
        if let Some(ref transport) = inner.transport {
            if let Some((version, is_unchanged)) = inner
                .opened_files
                .get(&canonical)
                .map(|doc| (doc.version, doc.text == text))
            {
                if !is_unchanged {
                    let next_version = version + 1;
                    transport
                        .notify(
                            "textDocument/didChange",
                            json!({
                                "textDocument": {
                                    "uri": uri.clone(),
                                    "version": next_version,
                                },
                                "contentChanges": [
                                    { "text": text.clone() }
                                ],
                            }),
                        )
                        .await?;
                    if let Some(doc) = inner.opened_files.get_mut(&canonical) {
                        doc.version = next_version;
                        doc.text = text;
                    }
                }
                return Ok(());
            }

            transport
                .notify(
                    "textDocument/didOpen",
                    json!({
                        "textDocument": {
                            "uri": uri,
                            "languageId": lang_id,
                            "version": 1,
                            "text": text,
                        }
                    }),
                )
                .await?;
            inner.opened_files.insert(
                canonical,
                OpenDocumentState {
                    version: 1,
                    text,
                },
            );
        }

        Ok(())
    }

    pub async fn go_to_definition(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Option<DefinitionLocation>> {
        self.ensure_file_open(file).await?;
        let inner = self.inner.lock().await;
        let transport = match &inner.transport {
            Some(t) => t,
            None => return Ok(None),
        };

        let resp = transport
            .request(
                "textDocument/definition",
                json!({
                    "textDocument": { "uri": path_to_uri(file) },
                    "position": { "line": line, "character": col },
                }),
            )
            .await?;

        let loc = if resp["result"].is_array() {
            resp["result"]
                .as_array()
                .and_then(|arr| arr.first())
                .cloned()
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
                let start_col = range["start"]["character"].as_u64().unwrap_or(0) as usize;
                return Ok(Some(DefinitionLocation {
                    file_path,
                    start_line,
                    start_col,
                }));
            }
        }

        Ok(None)
    }

    pub async fn find_references(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Vec<Reference>> {
        self.ensure_file_open(file).await?;
        let inner = self.inner.lock().await;
        let transport = match &inner.transport {
            Some(t) => t,
            None => return Ok(vec![]),
        };

        let resp = transport
            .request(
                "textDocument/references",
                json!({
                    "textDocument": { "uri": path_to_uri(file) },
                    "position": { "line": line, "character": col },
                    "context": { "includeDeclaration": true },
                }),
            )
            .await?;

        let mut refs = Vec::new();
        if let Some(arr) = resp["result"].as_array() {
            for loc in arr {
                if let (Some(uri), Some(range)) = (loc["uri"].as_str(), loc.get("range")) {
                    refs.push(Reference {
                        file_path: uri_to_path(uri),
                        line: range["start"]["line"].as_u64().unwrap_or(0) as usize,
                        col: range["start"]["character"].as_u64().unwrap_or(0) as usize,
                    });
                }
            }
        }

        Ok(refs)
    }

    pub async fn hover(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Option<HoverInfo>> {
        self.ensure_file_open(file).await?;
        let inner = self.inner.lock().await;
        let transport = match &inner.transport {
            Some(t) => t,
            None => return Ok(None),
        };

        let resp = transport
            .request(
                "textDocument/hover",
                json!({
                    "textDocument": { "uri": path_to_uri(file) },
                    "position": { "line": line, "character": col },
                }),
            )
            .await?;

        let contents = match resp["result"].get("contents") {
            Some(c) if c.is_string() => c.as_str().unwrap_or("").to_string(),
            Some(c) if c.is_object() => c["value"].as_str().unwrap_or("").to_string(),
            Some(c) if c.is_array() => {
                let empty = Vec::new();
                c.as_array()
                    .unwrap_or(&empty)
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

    pub async fn shutdown(&self) -> Result<()> {
        let inner = self.inner.lock().await;
        if let Some(transport) = &inner.transport {
            let _ = transport
                .request("shutdown", serde_json::Value::Null)
                .await;
            let _ = transport
                .notify("exit", serde_json::Value::Null)
                .await;
            tracing::info!("LSP server shut down: {}", inner.server);
        }
        Ok(())
    }
}

fn detect_language_id(path: &Path) -> &'static str {
    match path.extension().and_then(|e| e.to_str()) {
        Some("rs") => "rust",
        Some("py") => "python",
        Some("js") => "javascript",
        Some("jsx") => "javascriptreact",
        Some("ts") => "typescript",
        Some("tsx") => "typescriptreact",
        Some("go") => "go",
        Some("c") | Some("h") => "c",
        Some("cpp") | Some("hpp") | Some("cc") => "cpp",
        Some("java") => "java",
        Some("rb") => "ruby",
        Some("toml") => "toml",
        Some("json") => "json",
        Some("yaml") | Some("yml") => "yaml",
        Some("md") => "markdown",
        _ => "plaintext",
    }
}

fn path_to_uri(path: &Path) -> String {
    let canonical = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    Url::from_file_path(&canonical)
        .map(|u| u.to_string())
        .unwrap_or_else(|_| format!("file:///{}", canonical.display()))
}

pub(crate) fn uri_to_path(uri: &str) -> PathBuf {
    Url::parse(uri)
        .ok()
        .and_then(|u| u.to_file_path().ok())
        .unwrap_or_else(|| {
            let stripped = uri.strip_prefix("file://").unwrap_or(uri);
            PathBuf::from(stripped)
        })
}
