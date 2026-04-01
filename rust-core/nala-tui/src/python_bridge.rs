//! Python IPC bridge.
//!
//! Spawns a `python -m nala_orchestrator.cli` subprocess and communicates
//! with it over JSON-lines on stdin/stdout. Each natural-language query is
//! sent as a JSON request; the subprocess streams chunks back and signals
//! completion with a `done` message.
//!
//! The bridge runs as a persistent background task for the lifetime of the
//! application. Queries are sent through a `QuerySender` channel handle, and
//! responses arrive on the shared `BackgroundEvent` channel already owned by
//! `App`.
//!
//! ## Subprocess protocol (JSON-lines)
//!
//! ```text
//! → {"id":"1","type":"query","text":"...","project_root":"..."}
//! ← {"id":"1","type":"chunk","text":"..."}   (0..N)
//! ← {"id":"1","type":"done"}
//! ← {"id":"1","type":"error","text":"..."}
//!
//! → {"id":"2","type":"ping"}
//! ← {"id":"2","type":"pong","version":"0.1.0"}
//!
//! → {"id":"3","type":"index_context","total_files":10,"total_symbols":50}
//! ← {"id":"3","type":"ok"}
//! ```

use crate::app::BackgroundEvent;
use anyhow::{anyhow, Context, Result};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::mpsc;

// ── Request ID counter ─────────────────────────────────────────────────────

static NEXT_ID: AtomicU64 = AtomicU64::new(1);

fn next_id() -> String {
    NEXT_ID.fetch_add(1, Ordering::Relaxed).to_string()
}

// ── Request types ──────────────────────────────────────────────────────────

/// The kind of request to send to the Python subprocess.
pub enum BridgeRequest {
    /// Natural-language LLM query.
    Query { text: String, project_root: PathBuf },
    /// Run all analysis perspectives.
    RunPerspectives { project_root: PathBuf, perspective: String },
    /// List past sessions.
    ListSessions { project_root: PathBuf },
    /// Create a new session.
    NewSession,
    /// Load an existing session by ID.
    LoadSession { session_id: String },
    /// Get the current session summary.
    SessionSummary,
    /// Generate a mission document (optionally with a focus).
    GenerateMission { focus: String },
    /// Query with inline-action extraction enabled.
    QueryWithActions { text: String, project_root: PathBuf },
    /// Apply a previously proposed action.
    ApplyAction { action_id: String },
    /// Skip (discard) a proposed action.
    SkipAction { action_id: String },
}

// ── PythonBridge ───────────────────────────────────────────────────────────

/// Handle for sending requests to the background Python bridge task.
///
/// Clone freely — all clones share the same underlying channel.
#[derive(Clone)]
pub struct PythonBridge {
    request_tx: mpsc::Sender<BridgeRequest>,
}

impl PythonBridge {
    /// Send a natural-language query.
    pub async fn query(&self, text: String, project_root: PathBuf) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::Query { text, project_root })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Run all (or one named) analysis perspective.
    pub async fn run_perspectives(
        &self,
        project_root: PathBuf,
        perspective: &str,
    ) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::RunPerspectives {
                project_root,
                perspective: perspective.to_string(),
            })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// List past sessions.
    pub async fn list_sessions(&self, project_root: PathBuf) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::ListSessions { project_root })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Create a new session.
    pub async fn new_session(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::NewSession)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Load a session by ID.
    pub async fn load_session(&self, session_id: String) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::LoadSession { session_id })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Get the current session summary.
    pub async fn session_summary(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::SessionSummary)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Generate a mission document.
    pub async fn generate_mission(&self, focus: String) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::GenerateMission { focus })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Send a query with inline-action extraction enabled.
    pub async fn query_with_actions(&self, text: String, project_root: PathBuf) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::QueryWithActions { text, project_root })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Apply a previously proposed action.
    pub async fn apply_action(&self, action_id: String) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::ApplyAction { action_id })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Skip (discard) a proposed action.
    pub async fn skip_action(&self, action_id: String) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::SkipAction { action_id })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }
}

// ── spawn ──────────────────────────────────────────────────────────────────

/// Launch the Python IPC subprocess and return a `PythonBridge` handle.
///
/// The bridge task runs until the `PythonBridge` (and all its clones) are
/// dropped, at which point the subprocess stdin is closed and it exits cleanly.
///
/// * `project_root` — passed to the subprocess as `--root`
/// * `bg_tx`        — the `BackgroundEvent` sender already owned by `App`
pub async fn spawn(
    project_root: &PathBuf,
    bg_tx: mpsc::Sender<BackgroundEvent>,
) -> Result<PythonBridge> {
    let (query_tx, query_rx) = mpsc::channel::<BridgeRequest>(32);

    let root = project_root.clone();
    let root_str = root.to_string_lossy().to_string();

    // Spawn the subprocess
    let mut child = Command::new("python")
        .args(["-m", "nala_orchestrator.cli", "--root", &root_str])
        .env("PYTHONUNBUFFERED", "1")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null()) // suppress Python tracebacks in TUI
        .spawn()
        .context("Failed to spawn Python IPC subprocess. Is nala_orchestrator installed?")?;

    let stdin = child
        .stdin
        .take()
        .ok_or_else(|| anyhow!("Failed to take subprocess stdin"))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| anyhow!("Failed to take subprocess stdout"))?;

    // Wait for the "ready" message before accepting queries
    let (ready_tx, ready_rx) = tokio::sync::oneshot::channel::<Result<bool>>();

    // bg_tx_task goes into the spawned task; bg_tx_notify stays here for after ready
    let bg_tx_task = bg_tx.clone();
    let bg_tx_notify = bg_tx.clone();
    tokio::spawn(async move {
        if let Err(e) = bridge_task(child, stdin, stdout, query_rx, bg_tx_task, ready_tx).await {
            // Bridge crashed — notify the UI
            let _ = bg_tx
                .send(BackgroundEvent::AssistantError(format!(
                    "Python bridge error: {e}"
                )))
                .await;
        }
    });

    // Block until the subprocess signals ready (or fails)
    let has_llm = match ready_rx.await {
        Ok(Ok(v)) => v,
        Ok(Err(e)) => return Err(e),
        Err(_) => return Err(anyhow!("Python bridge task exited before signalling ready")),
    };

    // Notify the UI that the bridge is up
    let _ = bg_tx_notify
        .send(BackgroundEvent::BridgeReady { has_llm })
        .await;

    Ok(PythonBridge { request_tx: query_tx })
}

// ── bridge_task ────────────────────────────────────────────────────────────

/// Core background task: manages the subprocess lifecycle.
async fn bridge_task(
    mut child: Child,
    mut stdin: ChildStdin,
    stdout: ChildStdout,
    mut query_rx: mpsc::Receiver<BridgeRequest>,
    bg_tx: mpsc::Sender<BackgroundEvent>,
    ready_tx: tokio::sync::oneshot::Sender<Result<bool>>,
) -> Result<()> {
    let mut reader = BufReader::new(stdout).lines();

    // ── Wait for "ready" ───────────────────────────────────────────────────
    let has_llm = loop {
        match reader.next_line().await {
            Ok(Some(line)) => {
                if let Ok(msg) = serde_json::from_str::<Value>(&line) {
                    if msg.get("type").and_then(|t| t.as_str()) == Some("ready") {
                        let has_llm = msg
                            .get("has_llm")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false);
                        break has_llm;
                    }
                }
            }
            Ok(None) => {
                let _ = ready_tx.send(Err(anyhow!("Subprocess exited before sending ready")));
                return Ok(());
            }
            Err(e) => {
                let _ = ready_tx.send(Err(e.into()));
                return Ok(());
            }
        }
    };
    let _ = ready_tx.send(Ok(has_llm));

    // ── Main dispatch loop ─────────────────────────────────────────────────
    loop {
        tokio::select! {
            // Incoming request from the TUI
            maybe_req = query_rx.recv() => {
                match maybe_req {
                    None => break, // All PythonBridge handles dropped
                    Some(req) => {
                        let id = next_id();
                        let msg = match req {
                            BridgeRequest::Query { text, project_root } => json!({
                                "id": id,
                                "type": "query",
                                "text": text,
                                "project_root": project_root.to_string_lossy(),
                            }),
                            BridgeRequest::RunPerspectives { project_root, perspective } => json!({
                                "id": id,
                                "type": "run_perspectives",
                                "project_root": project_root.to_string_lossy(),
                                "perspective": perspective,
                            }),
                            BridgeRequest::ListSessions { project_root } => json!({
                                "id": id,
                                "type": "list_sessions",
                                "project_root": project_root.to_string_lossy(),
                            }),
                            BridgeRequest::NewSession => json!({
                                "id": id,
                                "type": "new_session",
                            }),
                            BridgeRequest::LoadSession { session_id } => json!({
                                "id": id,
                                "type": "load_session",
                                "session_id": session_id,
                            }),
                            BridgeRequest::SessionSummary => json!({
                                "id": id,
                                "type": "session_summary",
                            }),
                            BridgeRequest::GenerateMission { focus } => json!({
                                "id": id,
                                "type": "generate_mission",
                                "focus": focus,
                            }),
                            BridgeRequest::QueryWithActions { text, project_root } => json!({
                                "id": id,
                                "type": "query_with_actions",
                                "text": text,
                                "project_root": project_root.to_string_lossy(),
                            }),
                            BridgeRequest::ApplyAction { action_id } => json!({
                                "id": id,
                                "type": "apply_action",
                                "action_id": action_id,
                            }),
                            BridgeRequest::SkipAction { action_id } => json!({
                                "id": id,
                                "type": "skip_action",
                                "action_id": action_id,
                            }),
                        };
                        if let Err(e) = send_line(&mut stdin, &msg).await {
                            let _ = bg_tx.send(BackgroundEvent::AssistantError(
                                format!("Failed to send request: {e}")
                            )).await;
                        }
                    }
                }
            }

            // Response from the subprocess
            line = reader.next_line() => {
                match line {
                    Err(e) => {
                        let _ = bg_tx.send(BackgroundEvent::AssistantError(
                            format!("IPC read error: {e}")
                        )).await;
                        break;
                    }
                    Ok(None) => break, // subprocess exited
                    Ok(Some(raw)) => {
                        handle_response(&raw, &bg_tx).await;
                    }
                }
            }
        }
    }

    // Close stdin → subprocess exits cleanly
    drop(stdin);
    let _ = child.wait().await;
    Ok(())
}

// ── Helpers ────────────────────────────────────────────────────────────────

/// Write a JSON value as a single line to the subprocess stdin.
async fn send_line(stdin: &mut ChildStdin, msg: &Value) -> Result<()> {
    let mut line = serde_json::to_string(msg)?;
    line.push('\n');
    stdin.write_all(line.as_bytes()).await?;
    stdin.flush().await?;
    Ok(())
}

/// Parse one JSON-lines response and route it to the BackgroundEvent channel.
async fn handle_response(raw: &str, bg_tx: &mpsc::Sender<BackgroundEvent>) {
    let msg = match serde_json::from_str::<Value>(raw) {
        Ok(v) => v,
        Err(_) => return, // ignore malformed lines
    };

    let msg_type = msg.get("type").and_then(|t| t.as_str()).unwrap_or("");

    match msg_type {
        "chunk" => {
            let text = msg
                .get("text")
                .and_then(|t| t.as_str())
                .unwrap_or("")
                .to_string();
            if !text.is_empty() {
                let _ = bg_tx.send(BackgroundEvent::AssistantChunk(text)).await;
            }
        }
        "done" => {
            let _ = bg_tx.send(BackgroundEvent::AssistantDone).await;
        }
        "error" => {
            let text = msg
                .get("text")
                .and_then(|t| t.as_str())
                .unwrap_or("Unknown error")
                .to_string();
            let _ = bg_tx.send(BackgroundEvent::AssistantError(text)).await;
        }
        "proposed_action" => {
            let action_id = msg.get("action_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let action_type = msg.get("action_type").and_then(|v| v.as_str()).unwrap_or("edit").to_string();
            let description = msg.get("description").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let preview = msg.get("preview").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let _ = bg_tx.send(BackgroundEvent::ProposedAction {
                action_id,
                action_type,
                description,
                preview,
            }).await;
        }
        "action_applied" => {
            let action_id = msg.get("action_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let success = msg.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            let message = msg.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let output = msg.get("output").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let _ = bg_tx.send(BackgroundEvent::ActionApplied {
                action_id,
                success,
                message,
                output,
            }).await;
        }
        "sessions" => {
            // Format session list as a text block
            let sessions = msg.get("sessions").and_then(|v| v.as_array()).cloned().unwrap_or_default();
            let text = if sessions.is_empty() {
                "No sessions found. Start one by asking a question.".to_string()
            } else {
                let mut lines = vec!["**Past sessions** (newest first):".to_string()];
                for s in &sessions {
                    let id = s.get("session_id").and_then(|v| v.as_str()).unwrap_or("?");
                    let turns = s.get("total_turns").and_then(|v| v.as_u64()).unwrap_or(0);
                    let status = s.get("status").and_then(|v| v.as_str()).unwrap_or("?");
                    lines.push(format!("  • {} — {} turns, {}", id, turns, status));
                }
                lines.push("\nUse `/session load <id>` to resume a session.".to_string());
                lines.join("\n")
            };
            let _ = bg_tx.send(BackgroundEvent::AssistantChunk(text)).await;
            let _ = bg_tx.send(BackgroundEvent::AssistantDone).await;
        }
        "session_created" => {
            let session_id = msg.get("session_id").and_then(|v| v.as_str()).unwrap_or("?");
            let text = format!("New session created: **{}**", session_id);
            let _ = bg_tx.send(BackgroundEvent::AssistantChunk(text)).await;
            let _ = bg_tx.send(BackgroundEvent::AssistantDone).await;
        }
        "session_loaded" => {
            let session_id = msg.get("session_id").and_then(|v| v.as_str()).unwrap_or("?");
            let turns = msg.get("turn_count").and_then(|v| v.as_u64()).unwrap_or(0);
            let summary = msg.get("summary").and_then(|v| v.as_str()).unwrap_or("");
            let text = format!(
                "Session **{}** loaded ({} turns).{}",
                session_id,
                turns,
                if summary.is_empty() { String::new() } else { format!("\n{}", summary) }
            );
            let _ = bg_tx.send(BackgroundEvent::AssistantChunk(text)).await;
            let _ = bg_tx.send(BackgroundEvent::AssistantDone).await;
        }
        "session_summary" => {
            let text = msg
                .get("text")
                .and_then(|t| t.as_str())
                .unwrap_or("No session active.")
                .to_string();
            let _ = bg_tx.send(BackgroundEvent::AssistantChunk(text)).await;
            let _ = bg_tx.send(BackgroundEvent::AssistantDone).await;
        }
        // "pong", "ok", "ready" — informational, no UI event needed
        _ => {}
    }
}

/// Send an index context update to the Python subprocess (fire-and-forget).
pub async fn send_index_context(
    stdin: &mut ChildStdin,
    total_files: usize,
    total_symbols: usize,
) -> Result<()> {
    let id = next_id();
    let msg = json!({
        "id": id,
        "type": "index_context",
        "total_files": total_files,
        "total_symbols": total_symbols,
    });
    send_line(stdin, &msg).await
}
