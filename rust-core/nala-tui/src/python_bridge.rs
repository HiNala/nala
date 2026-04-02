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
use std::env;
use std::fs::{self, OpenOptions};
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
    /// Request a context window usage breakdown.
    ContextUsage,
    /// Trigger manual context compaction with optional focus hint.
    CompactContext { focus: String },
    /// Show Neo4j graph statistics.
    GraphStats,
    /// Start a multi-agent team run for the given objective.
    TeamStart { objective: String },
    /// Get status of the running / last team run.
    TeamStatus,
    /// Cancel the current team run.
    TeamCancel,
    /// Save a handoff document manually.
    HandoffSave,
    /// Show the most recent handoff document.
    HandoffShow,
    /// Show handoff chain history.
    HandoffHistory,
    /// Request memory summary.
    MemorySummary,
    /// List memory sessions.
    MemorySessions,
    /// Forget (clear) memory entries.
    MemoryForget { target: String },
    /// Update orchestrator-side index context.
    IndexContext {
        total_files: usize,
        total_symbols: usize,
        symbols: Vec<nala_indexer::Symbol>,
    },
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

    /// Request the current context window usage breakdown.
    pub async fn context_usage(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::ContextUsage)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Trigger manual context compaction.
    pub async fn compact_context(&self, focus: String) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::CompactContext { focus })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Show Neo4j graph statistics.
    pub async fn graph_stats(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::GraphStats)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Start a multi-agent team run.
    pub async fn team_start(&self, objective: String) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::TeamStart { objective })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Get team run status.
    pub async fn team_status(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::TeamStatus)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Cancel team run.
    pub async fn team_cancel(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::TeamCancel)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Save a handoff document.
    pub async fn handoff_save(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::HandoffSave)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Show latest handoff.
    pub async fn handoff_show(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::HandoffShow)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Show handoff history chain.
    pub async fn handoff_history(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::HandoffHistory)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Request memory summary.
    pub async fn memory_summary(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::MemorySummary)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// List memory sessions.
    pub async fn memory_sessions(&self) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::MemorySessions)
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Forget (clear) memory entries.
    pub async fn memory_forget(&self, target: String) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::MemoryForget { target })
            .await
            .map_err(|_| anyhow!("Python bridge has shut down"))
    }

    /// Send index context so Python can refresh retrieval and graph state.
    pub async fn index_context(
        &self,
        total_files: usize,
        total_symbols: usize,
        symbols: Vec<nala_indexer::Symbol>,
    ) -> Result<()> {
        self.request_tx
            .send(BridgeRequest::IndexContext {
                total_files,
                total_symbols,
                symbols,
            })
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
    project_root: &std::path::Path,
    bg_tx: mpsc::Sender<BackgroundEvent>,
) -> Result<PythonBridge> {
    let (query_tx, query_rx) = mpsc::channel::<BridgeRequest>(128);

    let root = project_root.to_path_buf();
    let root_str = root.to_string_lossy().to_string();

    // Spawn the subprocess
    let mut child = spawn_python_subprocess(&root_str)
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
    let (ready_tx, ready_rx) = tokio::sync::oneshot::channel::<Result<(bool, String, String)>>();

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

    let (has_llm, provider, model) = match ready_rx.await {
        Ok(Ok(v)) => v,
        Ok(Err(e)) => return Err(e),
        Err(_) => return Err(anyhow!("Python bridge task exited before signalling ready")),
    };

    let _ = bg_tx_notify
        .send(BackgroundEvent::BridgeReady { has_llm, provider, model })
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
    ready_tx: tokio::sync::oneshot::Sender<Result<(bool, String, String)>>,
) -> Result<()> {
    let mut reader = BufReader::new(stdout).lines();

    // ── Wait for "ready" ───────────────────────────────────────────────────
    let ready_info = loop {
        match reader.next_line().await {
            Ok(Some(line)) => {
                if let Ok(msg) = serde_json::from_str::<Value>(&line) {
                    if msg.get("type").and_then(|t| t.as_str()) == Some("ready") {
                        let has_llm = msg
                            .get("has_llm")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false);
                        let provider = msg
                            .get("provider")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        let model = msg
                            .get("model")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        break (has_llm, provider, model);
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
    let _ = ready_tx.send(Ok(ready_info));

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
                            BridgeRequest::ContextUsage => json!({
                                "id": id,
                                "type": "context_usage",
                            }),
                            BridgeRequest::CompactContext { focus } => json!({
                                "id": id,
                                "type": "compact_context",
                                "focus": focus,
                            }),
                            BridgeRequest::GraphStats => json!({
                                "id": id,
                                "type": "graph_stats",
                            }),
                            BridgeRequest::TeamStart { objective } => json!({
                                "id": id,
                                "type": "team_start",
                                "objective": objective,
                            }),
                            BridgeRequest::TeamStatus => json!({
                                "id": id,
                                "type": "team_status",
                            }),
                            BridgeRequest::TeamCancel => json!({
                                "id": id,
                                "type": "team_cancel",
                            }),
                            BridgeRequest::HandoffSave => json!({
                                "id": id,
                                "type": "handoff_save",
                            }),
                            BridgeRequest::HandoffShow => json!({
                                "id": id,
                                "type": "handoff_show",
                            }),
                            BridgeRequest::HandoffHistory => json!({
                                "id": id,
                                "type": "handoff_history",
                            }),
                            BridgeRequest::MemorySummary => json!({
                                "id": id,
                                "type": "memory_summary",
                            }),
                            BridgeRequest::MemorySessions => json!({
                                "id": id,
                                "type": "memory_sessions",
                            }),
                            BridgeRequest::MemoryForget { target } => json!({
                                "id": id,
                                "type": "memory_forget",
                                "target": target,
                            }),
                            BridgeRequest::IndexContext {
                                total_files,
                                total_symbols,
                                symbols,
                            } => json!({
                                "id": id,
                                "type": "index_context",
                                "total_files": total_files,
                                "total_symbols": total_symbols,
                                "symbols": symbols,
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

fn spawn_python_subprocess(root_str: &str) -> Result<Child> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(explicit) = env::var("NALA_PYTHON") {
        if !explicit.trim().is_empty() {
            candidates.push(PathBuf::from(explicit));
        }
    }

    let root = PathBuf::from(root_str);
    #[cfg(windows)]
    {
        candidates.push(root.join(".venv").join("Scripts").join("python.exe"));
    }
    #[cfg(not(windows))]
    {
        candidates.push(root.join(".venv").join("bin").join("python"));
    }

    if let Ok(venv) = env::var("VIRTUAL_ENV") {
        #[cfg(windows)]
        {
            candidates.push(PathBuf::from(&venv).join("Scripts").join("python.exe"));
        }
        #[cfg(not(windows))]
        {
            candidates.push(PathBuf::from(&venv).join("bin").join("python"));
        }
    }

    #[cfg(windows)]
    let fallback = vec![PathBuf::from("python"), PathBuf::from("py")];
    #[cfg(not(windows))]
    let fallback = vec![PathBuf::from("python3"), PathBuf::from("python")];
    candidates.extend(fallback);

    let mut last_err = None;
    for python_cmd in candidates {
        let mut cmd = Command::new(&python_cmd);
        if python_cmd.file_name().and_then(|s| s.to_str()) == Some("py") {
            cmd.args(["-3", "-m", "nala_orchestrator.cli", "--root", root_str]);
        } else {
            cmd.args(["-m", "nala_orchestrator.cli", "--root", root_str]);
        }
        let attempt = cmd
            .env("PYTHONUNBUFFERED", "1")
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(bridge_stderr_stdio(root_str))
            .spawn();
        match attempt {
            Ok(child) => return Ok(child),
            Err(e) => {
                last_err = Some((python_cmd, e));
            }
        }
    }

    if let Some((cmd, err)) = last_err {
        Err(anyhow!(
            "Failed to launch Python command '{}': {}",
            cmd.display(),
            err
        ))
    } else {
        Err(anyhow!("No Python command candidates were available"))
    }
}

fn bridge_stderr_stdio(root_str: &str) -> std::process::Stdio {
    let root = PathBuf::from(root_str);
    let log_dir = root.join(".nala").join("logs");
    if fs::create_dir_all(&log_dir).is_err() {
        return std::process::Stdio::null();
    }
    let path = log_dir.join("python-bridge.stderr.log");
    match OpenOptions::new().create(true).append(true).open(path) {
        Ok(file) => std::process::Stdio::from(file),
        Err(_) => std::process::Stdio::null(),
    }
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
        Err(e) => {
            eprintln!("[bridge] malformed JSON from Python: {e} — line: {}", &raw[..raw.len().min(200)]);
            let _ = bg_tx.send(BackgroundEvent::AssistantError(
                format!("Received malformed response from AI backend: {e}")
            )).await;
            return;
        }
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

