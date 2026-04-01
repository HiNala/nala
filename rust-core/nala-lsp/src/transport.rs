//! LSP stdio transport — Content-Length framing per the LSP specification.
//!
//! The Language Server Protocol communicates over stdin/stdout using HTTP-style
//! header framing:
//!
//! ```text
//! Content-Length: 123\r\n
//! \r\n
//! {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
//! ```
//!
//! This module provides an async `LspTransport` that:
//!   1. Spawns an LSP server child process.
//!   2. Encodes outgoing JSON-RPC messages with Content-Length framing.
//!   3. Decodes incoming Content-Length-framed responses.
//!   4. Matches responses to pending requests by id.

use anyhow::{anyhow, Context, Result};
use serde_json::Value;
use std::collections::HashMap;
use std::path::Path;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::{oneshot, Mutex};
use std::sync::{Arc, atomic::{AtomicI64, Ordering}};

// ── Message ID counter ────────────────────────────────────────────────────────

static NEXT_MSG_ID: AtomicI64 = AtomicI64::new(1);

fn next_msg_id() -> i64 {
    NEXT_MSG_ID.fetch_add(1, Ordering::Relaxed)
}

// ── Transport ─────────────────────────────────────────────────────────────────

/// Async LSP transport over a child process stdin/stdout.
pub struct LspTransport {
    stdin:    Arc<Mutex<ChildStdin>>,
    pending:  Arc<Mutex<HashMap<i64, oneshot::Sender<Value>>>>,
    _child:   Child,
}

impl LspTransport {
    /// Spawn an LSP server and return a transport handle.
    pub async fn spawn(server_cmd: &str, server_args: &[&str], project_root: &Path) -> Result<Self> {
        let mut cmd = Command::new(server_cmd);
        cmd.args(server_args)
            .current_dir(project_root)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null());

        let mut child = cmd.spawn()
            .with_context(|| format!("Failed to spawn LSP server '{server_cmd}'"))?;

        let stdin  = child.stdin.take().ok_or_else(|| anyhow!("Missing stdin"))?;
        let stdout = child.stdout.take().ok_or_else(|| anyhow!("Missing stdout"))?;

        let stdin   = Arc::new(Mutex::new(stdin));
        let pending: Arc<Mutex<HashMap<i64, oneshot::Sender<Value>>>> =
            Arc::new(Mutex::new(HashMap::new()));

        // Background task: read responses and dispatch to waiting callers.
        let pending_clone = Arc::clone(&pending);
        tokio::spawn(async move {
            if let Err(e) = Self::reader_task(stdout, pending_clone).await {
                tracing::debug!("LSP reader task ended: {e}");
            }
        });

        Ok(Self { stdin, pending, _child: child })
    }

    /// Send a request and wait for the matching response.
    pub async fn request(&self, method: &str, params: Value) -> Result<Value> {
        let id = next_msg_id();
        let (tx, rx) = oneshot::channel();

        {
            let mut p = self.pending.lock().await;
            p.insert(id, tx);
        }

        let msg = serde_json::json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });

        self.send_raw(&msg).await?;

        rx.await.map_err(|_| anyhow!("LSP server closed before responding"))
    }

    /// Send a notification (no response expected).
    pub async fn notify(&self, method: &str, params: Value) -> Result<()> {
        let msg = serde_json::json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        });
        self.send_raw(&msg).await
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    async fn send_raw(&self, msg: &Value) -> Result<()> {
        let body = serde_json::to_string(msg)?;
        let frame = format!("Content-Length: {}\r\n\r\n{}", body.len(), body);
        let mut stdin = self.stdin.lock().await;
        stdin.write_all(frame.as_bytes()).await?;
        stdin.flush().await?;
        Ok(())
    }

    async fn reader_task(
        stdout: ChildStdout,
        pending: Arc<Mutex<HashMap<i64, oneshot::Sender<Value>>>>,
    ) -> Result<()> {
        let mut reader = BufReader::new(stdout);
        let mut header_buf = String::new();

        loop {
            // Read headers until blank line.
            let mut content_length: Option<usize> = None;
            loop {
                header_buf.clear();
                let n = reader.read_line(&mut header_buf).await?;
                if n == 0 {
                    return Ok(()); // EOF
                }
                let line = header_buf.trim();
                if line.is_empty() {
                    break; // End of headers.
                }
                if let Some(rest) = line.strip_prefix("Content-Length:") {
                    content_length = rest.trim().parse().ok();
                }
            }

            let len = content_length.ok_or_else(|| anyhow!("Missing Content-Length header"))?;
            let mut body = vec![0u8; len];
            tokio::io::AsyncReadExt::read_exact(&mut reader, &mut body).await?;

            let msg: Value = serde_json::from_slice(&body)?;

            // Dispatch responses to waiting request callers.
            if let Some(id) = msg.get("id").and_then(|v| v.as_i64()) {
                let mut p = pending.lock().await;
                if let Some(tx) = p.remove(&id) {
                    let _ = tx.send(msg);
                }
            }
            // Notifications (no id) are currently discarded.
        }
    }
}
