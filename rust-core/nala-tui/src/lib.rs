//! nala-tui: Ratatui-based terminal user interface.
//!
//! Entry point is `run(project_root)`. The TUI owns the async event loop,
//! renders at ~30fps, and coordinates all panels and state transitions.
//!
//! Architecture:
//! - `app.rs`              — App state machine and event dispatch
//! - `ui/splash.rs`        — Boot splash screen
//! - `ui/layout.rs`        — Top-level layout composition
//! - `ui/command_bar.rs`   — Command input widget
//! - `ui/status_bar.rs`    — Bottom status bar
//! - `ui/file_panel.rs`    — Collapsible file tree panel
//! - `ui/session_panel.rs` — Collapsible session history panel

pub mod actions;
pub mod app;
pub mod commands;
pub mod lsp_commands;
pub mod python_bridge;
pub mod ui;

use anyhow::Result;
use std::path::Path;

/// Launch the Nala terminal user interface.
///
/// Blocks until the user quits (Ctrl+C, Ctrl+Q, or /quit).
pub async fn run(project_root: &Path) -> Result<()> {
    let mut app = app::App::new(project_root)?;
    app.run().await
}
