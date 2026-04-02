//! LSP-related command handlers.
//!
//! Uses the persistent LspHandle stored on App instead of creating
//! throwaway LSP clients per command. Sends didOpen for queried files
//! automatically so servers can provide accurate results.

use crate::app::{App, AppMode, BackgroundEvent, Message};
use std::path::{Path, PathBuf};

impl App {
    pub(crate) fn lsp_status(&mut self) {
        let initialized = self.lsp_initialized;
        let errors = self.diagnostics_store.error_count();
        let warnings = self.diagnostics_store.warning_count();

        let Some(handle) = self.lsp_handle.clone() else {
            self.push_message(Message::system(
                "LSP: not started (run /scan first)".to_string(),
            ));
            return;
        };

        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            let server = handle.server_name().await;
            let status = if initialized { "running" } else { "not started" };
            let msg = format!(
                "LSP: {} ({})\n  Errors: {} | Warnings: {}",
                server, status, errors, warnings
            );
            let _ = tx.send(BackgroundEvent::AssistantChunk(msg)).await;
            let _ = tx.send(BackgroundEvent::AssistantDone).await;
        });
    }

    pub(crate) fn lsp_definition(&mut self, spec: String) {
        self.run_lsp_lookup(spec, "def");
    }

    pub(crate) fn lsp_references(&mut self, spec: String) {
        self.run_lsp_lookup(spec, "refs");
    }

    pub(crate) fn lsp_hover(&mut self, spec: String) {
        self.run_lsp_lookup(spec, "hover");
    }

    fn run_lsp_lookup(&mut self, spec: String, mode: &str) {
        let Some((file, line, col)) = parse_location_spec(&self.project_root, &spec) else {
            self.push_message(Message::error(format!(
                "Invalid location. Use: /{} <relative/path.ext:line:col>",
                mode
            )));
            return;
        };

        let Some(handle) = self.lsp_handle.clone() else {
            self.push_message(Message::error(
                "LSP not available. Run /index first to start the language server.".to_string(),
            ));
            return;
        };

        if !self.lsp_initialized {
            self.push_message(Message::error(
                "LSP is still initializing. Try again in a moment.".to_string(),
            ));
            return;
        }

        let tx = self.bg_tx.clone();
        let mode = mode.to_string();
        self.mode = AppMode::Analyzing;
        tokio::spawn(async move {
            let output = match mode.as_str() {
                "def" => match handle.go_to_definition(&file, line, col).await {
                    Ok(Some(def)) => format!(
                        "Definition: {}:{}:{}",
                        def.file_path.display(),
                        def.start_line + 1,
                        def.start_col + 1
                    ),
                    Ok(None) => "No definition found.".to_string(),
                    Err(e) => format!("LSP definition error: {}", e),
                },
                "refs" => match handle.find_references(&file, line, col).await {
                    Ok(refs) if refs.is_empty() => "No references found.".to_string(),
                    Ok(refs) => {
                        let mut lines = vec![format!("Found {} references:", refs.len())];
                        for r in refs.into_iter().take(30) {
                            lines.push(format!(
                                "  - {}:{}:{}",
                                r.file_path.display(),
                                r.line + 1,
                                r.col + 1
                            ));
                        }
                        lines.join("\n")
                    }
                    Err(e) => format!("LSP references error: {}", e),
                },
                "hover" => match handle.hover(&file, line, col).await {
                    Ok(Some(h)) => format!("Hover:\n{}", h.contents),
                    Ok(None) => "No hover information found.".to_string(),
                    Err(e) => format!("LSP hover error: {}", e),
                },
                _ => "Unsupported LSP mode.".to_string(),
            };

            let _ = tx.send(BackgroundEvent::AssistantChunk(output)).await;
            let _ = tx.send(BackgroundEvent::AssistantDone).await;
        });
    }
}

fn parse_location_spec(project_root: &Path, spec: &str) -> Option<(PathBuf, usize, usize)> {
    let raw = spec.trim();
    if raw.is_empty() {
        return None;
    }
    let mut parts = raw.rsplitn(3, ':');
    let col = parts.next()?.parse::<usize>().ok()?;
    let line = parts.next()?.parse::<usize>().ok()?;
    let file_part = parts.next()?;
    let file = project_root.join(file_part);
    if line == 0 || col == 0 {
        return None;
    }
    Some((file, line - 1, col - 1))
}
