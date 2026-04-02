//! LSP-related command handlers.
//!
//! Extracted from `app.rs` so LSP lookups and status queries live in
//! their own focused module.

use crate::app::{App, BackgroundEvent, Message};
use std::path::PathBuf;

impl App {
    pub(crate) fn lsp_status(&mut self) {
        let root = self.project_root.clone();
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            let manager = nala_lsp::LspManager::new(&root);
            let server = manager.server().to_string();
            let msg = format!("Detected LSP server: {}", server);
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

        let root = self.project_root.clone();
        let tx = self.bg_tx.clone();
        let mode = mode.to_string();
        tokio::spawn(async move {
            let mut manager = nala_lsp::LspManager::new(&root);
            if let Err(e) = manager.initialize().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
                return;
            }

            let output = match mode.as_str() {
                "def" => match manager.go_to_definition(&file, line, col).await {
                    Ok(Some(def)) => format!(
                        "Definition: {}:{}:{}",
                        def.file_path.display(),
                        def.start_line,
                        def.start_col
                    ),
                    Ok(None) => "No definition found.".to_string(),
                    Err(e) => format!("LSP definition error: {}", e),
                },
                "refs" => match manager.find_references(&file, line, col).await {
                    Ok(refs) if refs.is_empty() => "No references found.".to_string(),
                    Ok(refs) => {
                        let mut lines = vec![format!("Found {} references:", refs.len())];
                        for r in refs.into_iter().take(30) {
                            lines.push(format!(
                                "  - {}:{}:{}",
                                r.file_path.display(),
                                r.line,
                                r.col
                            ));
                        }
                        lines.join("\n")
                    }
                    Err(e) => format!("LSP references error: {}", e),
                },
                "hover" => match manager.hover(&file, line, col).await {
                    Ok(Some(h)) => format!("Hover:\n{}", h.contents),
                    Ok(None) => "No hover information found.".to_string(),
                    Err(e) => format!("LSP hover error: {}", e),
                },
                _ => "Unsupported LSP mode.".to_string(),
            };

            let _ = manager.shutdown().await;
            let _ = tx.send(BackgroundEvent::AssistantChunk(output)).await;
            let _ = tx.send(BackgroundEvent::AssistantDone).await;
        });
    }
}

/// Parse a `file:line:col` location spec into (absolute path, 0-based line, 0-based col).
fn parse_location_spec(project_root: &PathBuf, spec: &str) -> Option<(PathBuf, usize, usize)> {
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
