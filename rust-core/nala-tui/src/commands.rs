//! Slash-command dispatch and bridge-backed command handlers.
//!
//! Extracted from `app.rs` to keep the main state module focused on
//! the event loop and state transitions.

use crate::app::{App, AppMode, BackgroundEvent, Message};
use std::env;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

impl App {
    pub(crate) fn handle_slash_command(&mut self, cmd: &str) {
        let parts: Vec<&str> = cmd.splitn(2, ' ').collect();
        match parts[0] {
            "/help" => self.show_help(),
            "/quit" | "/exit" => {
                self.should_quit = true;
            }
            "/scan" => {
                self.push_message(Message::system(
                    "Scanning project files (hash-only, no parsing)...",
                ));
                self.index_progress = Some(0.2);
                self.start_background_scan();
            }
            "/index" => {
                self.push_message(Message::system(
                    "Indexing project (parse + symbols + metrics)...",
                ));
                self.index_progress = Some(0.2);
                self.start_background_index();
            }
            "/analyze" | "/analyse" => {
                let perspective = parts.get(1).copied().unwrap_or("all").to_string();
                self.run_perspectives(perspective);
            }
            "/scope" => {
                let args = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.set_analysis_scope(args);
            }
            "/lsp" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                if args == "status" {
                    self.lsp_status();
                } else {
                    self.push_message(Message::error("Usage: /lsp status"));
                }
            }
            "/def" => {
                let spec = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.lsp_definition(spec);
            }
            "/refs" => {
                let spec = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.lsp_references(spec);
            }
            "/hover" => {
                let spec = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.lsp_hover(spec);
            }
            "/memory" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.handle_memory_command(args);
            }
            "/doctor" => self.doctor(),
            "/session" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.handle_session_command(args);
            }
            "/generate" => {
                let focus = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.generate_mission(focus);
            }
            // ── /agent: primary autonomous workflow entrypoint ────────────
            "/agent" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.handle_agent_command(args);
            }
            // ── Deprecated aliases → route to /agent with hint ───────────
            "/act" => {
                let query = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.push_message(Message::system(
                    "Hint: /act is now /agent <instruction>. Routing for you.",
                ));
                if query.is_empty() {
                    self.push_message(Message::error("Usage: /agent <instruction>"));
                } else {
                    self.handle_agent_command(&query);
                }
            }
            "/task" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.push_message(Message::system(
                    "Hint: /task is now part of /agent. Routing for you.",
                ));
                match args {
                    "" | "status" => self.task_status(),
                    "list" => self.task_list(),
                    "done" => self.task_done(String::new()),
                    _ => {
                        if args.starts_with("done ") {
                            self.task_done(args.strip_prefix("done ").unwrap_or("").to_string());
                        } else {
                            self.task_create(args.to_string());
                        }
                    }
                }
            }
            "/team" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.push_message(Message::system(
                    "Hint: /team is now internal to /agent. Routing for you.",
                ));
                match args {
                    "status" => self.team_status(),
                    "cancel" => self.team_cancel(),
                    "" => self.push_message(Message::error(
                        "Usage: /agent <objective>  |  /agent status  |  /agent stop",
                    )),
                    objective => self.team_start(objective.to_string()),
                }
            }
            "/brain" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.push_message(Message::system(
                    "Hint: /brain is now /agent. Routing for you.",
                ));
                self.handle_agent_command(args);
            }
            "/diff" => {
                self.push_message(Message::system(
                    "Hint: /diff is now /agent review. Routing for you.",
                ));
                self.git_diff();
            }
            "/branch" => {
                self.push_message(Message::system(
                    "Hint: /branch is now part of /agent status. Routing for you.",
                ));
                self.git_branch();
            }
            "/status" => {
                self.push_message(Message::system(
                    "Hint: /status is now /agent status. Routing for you.",
                ));
                self.git_status();
            }
            // ── Stable commands ──────────────────────────────────────────
            "/context" => self.show_context_usage(),
            "/compact" => {
                let focus = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.compact_context(focus);
            }
            "/dashboard" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.handle_dashboard_command(args);
            }
            "/graph" => self.graph_stats(),
            "/handoff" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                match args {
                    "save" => self.handoff_save(),
                    "history" => self.handoff_history(),
                    _ => self.handoff_show(),
                }
            }
            "/diag" | "/diagnostics" => {
                self.show_diagnostics(parts.get(1).copied().unwrap_or(""));
            }
            "/clear" => {
                self.messages.clear();
            }
            "/undo" => self.undo_actions(),
            "/tree" | "/files" => {
                self.show_file_tree();
            }
            "/read" => {
                let path = parts.get(1).copied().unwrap_or("").trim().to_string();
                if path.is_empty() {
                    self.push_message(Message::error("Usage: /read <file_path>"));
                } else {
                    self.read_file(path);
                }
            }
            _ => {
                self.push_message(Message::error(format!(
                    "Unknown command: {}. Type /help.",
                    parts[0]
                )));
            }
        }
    }

    fn show_help(&mut self) {
        self.push_message(Message::assistant(concat!(
            "## Agent Workflow\n",
            "  /agent                 — show agent help and current run status\n",
            "  /agent <objective>     — start objective-driven agent run\n",
            "  /agent plan [topic]    — create or refresh a plan\n",
            "  /agent run             — execute the current plan\n",
            "  /agent review          — review current diff and pending changes\n",
            "  /agent verify          — run verification analysis\n",
            "  /agent hotspot         — quick hotspot triage\n",
            "  /agent status          — show objective, phase, tasks, git state\n",
            "  /agent stop            — cancel the active run\n\n",
            "## Code Intelligence\n",
            "  /analyze               — run all analysis perspectives\n",
            "  /analyze quick         — fast subset (complexity/security/dependency)\n",
            "  /scope <path>          — focus analysis on a subtree\n",
            "  /def <file:l:c>        — LSP go-to-definition\n",
            "  /refs <file:l:c>       — LSP find-references\n",
            "  /hover <file:l:c>      — LSP hover docs\n",
            "  /diag                  — show LSP diagnostics\n",
            "  /graph                 — code graph statistics\n",
            "  /read <file>           — display file contents in chat\n",
            "  /tree                  — show project file tree\n\n",
            "## Session & Memory\n",
            "  /session               — list past sessions\n",
            "  /session new           — start a fresh session\n",
            "  /session load <id>     — resume a past session\n",
            "  /memory                — show memory summary\n",
            "  /context               — show context window usage\n",
            "  /compact               — compact context to free tokens\n",
            "  /handoff               — show session handoff document\n\n",
            "## Utilities\n",
            "  /scan                  — quick file scan (hash-only)\n",
            "  /index                 — full index (parse + symbols)\n",
            "  /generate              — generate mission doc from findings\n",
            "  /dashboard             — start local dashboard\n",
            "  /undo                  — revert last applied actions\n",
            "  /doctor                — environment diagnostics\n",
            "  /clear                 — clear messages\n",
            "  /help                  — this help\n",
            "  /quit                  — exit\n\n",
            "## Key Bindings\n",
            "  Up/Down arrows         — cycle command history\n",
            "  Shift+Up/Down          — scroll messages\n",
            "  PgUp/PgDn              — scroll messages (larger jump)\n",
            "  Mouse wheel            — scroll messages\n",
            "  Ctrl+B                 — toggle file panel\n",
            "  Ctrl+E                 — toggle session panel\n",
            "  Esc                    — cancel / clear input\n\n",
            "Or just type a question to ask the AI.",
        )));
    }

    fn show_file_tree(&mut self) {
        let root = &self.project_root;
        let skip: std::collections::HashSet<&str> = [
            ".git", "node_modules", "__pycache__", ".nala", "target",
            "dist", "build", ".next", ".venv", "venv", ".mypy_cache",
            ".ruff_cache", ".pytest_cache",
        ].into_iter().collect();

        let mut lines = Vec::new();
        lines.push(format!("{}/", root.file_name().unwrap_or_default().to_string_lossy()));
        Self::walk_tree(root, "", &skip, &mut lines, 0, 60);
        self.push_message(Message::assistant(lines.join("\n")));
    }

    fn walk_tree(
        dir: &Path,
        prefix: &str,
        skip: &std::collections::HashSet<&str>,
        lines: &mut Vec<String>,
        depth: usize,
        max_lines: usize,
    ) {
        if lines.len() >= max_lines || depth > 3 {
            return;
        }
        let Ok(entries) = std::fs::read_dir(dir) else { return };
        let mut entries: Vec<_> = entries.filter_map(|e| e.ok()).collect();
        entries.sort_by(|a, b| {
            let a_dir = a.file_type().map(|f| f.is_dir()).unwrap_or(false);
            let b_dir = b.file_type().map(|f| f.is_dir()).unwrap_or(false);
            b_dir.cmp(&a_dir).then(a.file_name().cmp(&b.file_name()))
        });
        let entries: Vec<_> = entries.into_iter().filter(|e| {
            let name = e.file_name();
            let name = name.to_string_lossy();
            !name.starts_with('.') && !skip.contains(name.as_ref())
        }).collect();
        let total = entries.len();
        for (i, entry) in entries.into_iter().enumerate() {
            if lines.len() >= max_lines {
                lines.push(format!("{prefix}..."));
                return;
            }
            let is_last = i == total - 1;
            let connector = if is_last { "└── " } else { "├── " };
            let is_dir = entry.file_type().map(|f| f.is_dir()).unwrap_or(false);
            let name = entry.file_name();
            let suffix = if is_dir { "/" } else { "" };
            lines.push(format!("{prefix}{connector}{}{suffix}", name.to_string_lossy()));
            if is_dir {
                let ext = if is_last { "    " } else { "│   " };
                Self::walk_tree(&entry.path(), &format!("{prefix}{ext}"), skip, lines, depth + 1, max_lines);
            }
        }
    }

    fn read_file(&mut self, path: String) {
        let abs = if Path::new(&path).is_absolute() {
            PathBuf::from(&path)
        } else {
            self.project_root.join(&path)
        };
        if !abs.exists() {
            self.push_message(Message::error(format!(
                "File not found: {}",
                abs.display()
            )));
            return;
        }
        if abs.is_dir() {
            self.push_message(Message::error(format!(
                "{} is a directory. Use /tree to browse.",
                path
            )));
            return;
        }
        match std::fs::read_to_string(&abs) {
            Ok(content) => {
                let line_count = content.lines().count();
                let display = abs
                    .strip_prefix(&self.project_root)
                    .unwrap_or(&abs)
                    .display();
                let truncated = if line_count > 200 {
                    let first_200: String = content.lines().take(200)
                        .collect::<Vec<_>>()
                        .join("\n");
                    format!(
                        "**{}** ({} lines, showing first 200)\n```\n{}\n```\n\n... truncated ({} more lines)",
                        display, line_count, first_200, line_count - 200,
                    )
                } else {
                    format!(
                        "**{}** ({} lines)\n```\n{}\n```",
                        display, line_count, content,
                    )
                };
                self.push_message(Message::assistant(truncated));
            }
            Err(e) => {
                self.push_message(Message::error(format!(
                    "Cannot read {}: {}",
                    path, e
                )));
            }
        }
    }

    pub(crate) fn run_perspectives(&mut self, perspective: String) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system(
                "AI bridge is starting up — please wait a moment and try again.",
            ));
            return;
        };
        let root = if let Some(scope) = &self.analysis_scope {
            self.project_root.join(scope)
        } else {
            self.project_root.clone()
        };
        if !root.exists() {
            self.push_message(Message::error(format!(
                "Scope path does not exist: {}",
                root.display()
            )));
            return;
        }
        let tx = self.bg_tx.clone();
        self.mode = AppMode::Analyzing;
        self.push_message(Message::system(format!(
            "Running {} analysis...",
            if perspective == "all" {
                "full".to_string()
            } else {
                perspective.clone()
            }
        )));
        tokio::spawn(async move {
            if let Err(e) = bridge.run_perspectives(root, &perspective).await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    pub(crate) fn set_analysis_scope(&mut self, raw: String) {
        let trimmed = raw.trim();
        if trimmed.is_empty() {
            let current = self
                .analysis_scope
                .clone()
                .unwrap_or_else(|| "<project root>".to_string());
            self.push_message(Message::assistant(format!(
                "Current analysis scope: {}",
                current
            )));
            return;
        }
        if trimmed.eq_ignore_ascii_case("clear") {
            self.analysis_scope = None;
            self.push_message(Message::system("Analysis scope reset to full project."));
            return;
        }
        let candidate = self.project_root.join(trimmed);
        if !candidate.exists() {
            self.push_message(Message::error(format!(
                "Scope path not found: {}",
                candidate.display()
            )));
            return;
        }
        self.analysis_scope = Some(trimmed.to_string());
        self.push_message(Message::system(format!("Analysis scope set: {}", trimmed)));
    }

    pub(crate) fn send_llm_query(&mut self, text: String) {
        match &self.python_bridge {
            None => {
                self.push_message(Message::system(
                    "AI bridge is starting up — please wait a moment and try again.",
                ));
            }
            Some(bridge) => {
                let bridge = bridge.clone();
                let root = self.project_root.clone();
                let tx = self.bg_tx.clone();
                self.mode = AppMode::Analyzing;
                tokio::spawn(async move {
                    if let Err(e) = bridge.query(text, root).await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
        }
    }

    #[allow(dead_code)]
    pub(crate) fn send_action_query(&mut self, text: String) {
        match &self.python_bridge {
            None => {
                self.push_message(Message::system("AI bridge not ready."));
            }
            Some(bridge) => {
                let bridge = bridge.clone();
                let root = self.project_root.clone();
                let tx = self.bg_tx.clone();
                self.mode = AppMode::Analyzing;
                self.push_message(Message::system("Thinking... (action mode)"));
                tokio::spawn(async move {
                    if let Err(e) = bridge.query_with_actions(text, root).await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
        }
    }

    fn show_context_usage(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.context_usage().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    fn compact_context(&mut self, focus: String) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.push_message(Message::system("Compacting context window..."));
        tokio::spawn(async move {
            if let Err(e) = bridge.compact_context(focus).await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    fn handle_session_command(&mut self, args: &str) {
        let parts: Vec<&str> = args.split_whitespace().collect();
        let subcommand = parts.first().copied().unwrap_or("");
        match subcommand {
            "" => {
                let Some(bridge) = self.python_bridge.clone() else {
                    self.push_message(Message::system("AI bridge not ready."));
                    return;
                };
                let root = self.project_root.clone();
                let tx = self.bg_tx.clone();
                self.push_message(Message::system("Fetching sessions..."));
                tokio::spawn(async move {
                    if let Err(e) = bridge.list_sessions(root).await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
            "new" => {
                let Some(bridge) = self.python_bridge.clone() else {
                    self.push_message(Message::system("AI bridge not ready."));
                    return;
                };
                let tx = self.bg_tx.clone();
                tokio::spawn(async move {
                    if let Err(e) = bridge.new_session().await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
            "load" => {
                let session_id = parts.get(1).copied().unwrap_or("").trim().to_string();
                if session_id.is_empty() {
                    self.push_message(Message::error("Usage: /session load <session_id>"));
                    return;
                }
                let Some(bridge) = self.python_bridge.clone() else {
                    self.push_message(Message::system("AI bridge not ready."));
                    return;
                };
                let tx = self.bg_tx.clone();
                self.push_message(Message::system(format!(
                    "Loading session {}...",
                    session_id
                )));
                tokio::spawn(async move {
                    if let Err(e) = bridge.load_session(session_id).await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
            "compare" => {
                let older = parts.get(1).copied().unwrap_or("").trim().to_string();
                let newer = parts.get(2).copied().unwrap_or("").trim().to_string();
                if older.is_empty() || newer.is_empty() {
                    self.push_message(Message::error(
                        "Usage: /session compare <older_id> <newer_id>",
                    ));
                    return;
                }
                let Some(bridge) = self.python_bridge.clone() else {
                    self.push_message(Message::system("AI bridge not ready."));
                    return;
                };
                let tx = self.bg_tx.clone();
                self.push_message(Message::system(format!(
                    "Comparing sessions {} -> {}...",
                    older, newer
                )));
                tokio::spawn(async move {
                    if let Err(e) = bridge.session_compare(older, newer).await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
            "summary" => {
                let Some(bridge) = self.python_bridge.clone() else {
                    self.push_message(Message::system("AI bridge not ready."));
                    return;
                };
                let tx = self.bg_tx.clone();
                tokio::spawn(async move {
                    if let Err(e) = bridge.session_summary().await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
            _ => {
                self.push_message(Message::error(format!(
                    "Unknown session subcommand: '{}'. Use: list, new, load <id>, compare <a> <b>, summary.",
                    subcommand
                )));
            }
        }
    }

    fn handle_dashboard_command(&mut self, args: &str) {
        match args {
            "" | "start" => self.start_dashboard(self.dashboard_default_port),
            "stop" => self.stop_dashboard(),
            "status" => self.show_dashboard_status(),
            other => {
                if let Some(port_str) = other.strip_prefix("start ") {
                    match port_str.trim().parse::<u16>() {
                        Ok(port) => self.start_dashboard(port),
                        Err(_) => self.push_message(Message::error(
                            "Usage: /dashboard [start <port>] | stop | status",
                        )),
                    }
                } else if let Ok(port) = other.parse::<u16>() {
                    self.start_dashboard(port);
                } else {
                    self.push_message(Message::error(
                        "Usage: /dashboard [start <port>] | stop | status",
                    ));
                }
            }
        }
    }

    fn generate_mission(&mut self, focus: String) {
        match &self.python_bridge {
            None => self.push_message(Message::system("AI bridge not ready.")),
            Some(bridge) => {
                let bridge = bridge.clone();
                let tx = self.bg_tx.clone();
                self.mode = AppMode::Analyzing;
                let label = if focus.is_empty() {
                    if self.llm_available {
                        "Generating mission document...".to_string()
                    } else {
                        "Generating mission document from saved findings...".to_string()
                    }
                } else {
                    format!("Generating mission focused on: {}...", focus)
                };
                self.push_message(Message::system(label));
                tokio::spawn(async move {
                    if let Err(e) = bridge.generate_mission(focus).await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
        }
    }

    fn graph_stats(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.push_message(Message::system("Fetching graph statistics..."));
        tokio::spawn(async move {
            if let Err(e) = bridge.graph_stats().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    fn start_dashboard(&mut self, port: u16) {
        if self.dashboard_is_running() {
            let current_port = self.dashboard_port.unwrap_or(port);
            self.push_message(Message::system(format!(
                "Dashboard already running at http://127.0.0.1:{}",
                current_port
            )));
            return;
        }

        let Some(repo_root) = self.resolve_dashboard_repo_root() else {
            self.push_message(Message::error(
                "Could not find the dashboard files. Expected `dashboard/server.py` in this repo.",
            ));
            return;
        };

        let root_for_env = self
            .project_root
            .to_string_lossy()
            .trim_start_matches(r"\\?\")
            .to_string();
        let mut last_error = None;
        for python_cmd in dashboard_python_candidates(&repo_root) {
            let mut cmd = Command::new(&python_cmd);
            if python_cmd.file_name().and_then(|s| s.to_str()) == Some("py") {
                cmd.args([
                    "-3",
                    "-m",
                    "uvicorn",
                    "dashboard.server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    &port.to_string(),
                ]);
            } else {
                cmd.args([
                    "-m",
                    "uvicorn",
                    "dashboard.server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    &port.to_string(),
                ]);
            }

            match cmd
                .env("DASHBOARD_PORT", port.to_string())
                .env("NALA_PROJECT_ROOT", &root_for_env)
                .current_dir(&repo_root)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
            {
                Ok(child) => {
                    self.dashboard_process = Some(child);
                    self.dashboard_port = Some(port);
                    let url = format!("http://127.0.0.1:{}", port);
                    self.push_message(Message::system(format!("Dashboard started: {}", url)));
                    open_dashboard_in_browser(&url);
                    return;
                }
                Err(e) => last_error = Some((python_cmd.display().to_string(), e.to_string())),
            }
        }

        if let Some((cmd, err)) = last_error {
            self.push_message(Message::error(format!(
                "Failed to start dashboard via '{}': {}. Install `uvicorn` and `fastapi` in your Python env.",
                cmd, err
            )));
        }
    }

    fn stop_dashboard(&mut self) {
        if let Some(mut child) = self.dashboard_process.take() {
            let _ = child.kill();
            let _ = child.wait();
            let port = self
                .dashboard_port
                .take()
                .unwrap_or(self.dashboard_default_port);
            self.push_message(Message::system(format!(
                "Dashboard stopped (port {}).",
                port
            )));
        } else {
            self.push_message(Message::system("Dashboard is not running."));
        }
    }

    fn show_dashboard_status(&mut self) {
        if self.dashboard_is_running() {
            let port = self.dashboard_port.unwrap_or(self.dashboard_default_port);
            self.push_message(Message::assistant(format!(
                "Dashboard is running at http://127.0.0.1:{}",
                port
            )));
        } else {
            self.push_message(Message::assistant(
                "Dashboard is not running. Use `/dashboard` to start it.",
            ));
        }
    }

    fn dashboard_is_running(&mut self) -> bool {
        let Some(child) = self.dashboard_process.as_mut() else {
            return false;
        };

        match child.try_wait() {
            Ok(None) => true,
            Ok(Some(_)) | Err(_) => {
                self.dashboard_process = None;
                self.dashboard_port = None;
                false
            }
        }
    }

    fn resolve_dashboard_repo_root(&self) -> Option<PathBuf> {
        let mut candidates = vec![self.project_root.clone()];
        if let Ok(exe) = env::current_exe() {
            if let Some(dir) = exe.parent() {
                candidates.push(dir.join("..").join("..").join(".."));
            }
        }

        candidates
            .into_iter()
            .map(|p| p.canonicalize().unwrap_or(p))
            .find(|root| root.join("dashboard").join("server.py").exists())
    }

    pub(crate) fn doctor(&mut self) {
        let llm_status = if self.llm_available {
            "configured"
        } else {
            "not configured"
        };
        let bridge = if self.python_bridge.is_some() {
            "connected"
        } else {
            "not ready"
        };
        let scope = self
            .analysis_scope
            .clone()
            .unwrap_or_else(|| "<project root>".to_string());
        let lsp_status = if self.lsp_initialized {
            if self.lsp_server_name.is_empty() {
                "running".to_string()
            } else {
                format!("running ({})", self.lsp_server_name)
            }
        } else if self.lsp_handle.is_some() {
            "initializing...".to_string()
        } else {
            "not started (run /index)".to_string()
        };
        let provider_str = if self.llm_provider.is_empty() {
            "none".to_string()
        } else {
            format!("{} / {}", self.llm_provider, self.llm_model)
        };
        let mut text = format!(
            "Environment diagnostics:\n\
             \x20 Project root:    {}\n\
             \x20 Analysis scope:  {}\n\
             \x20 Python bridge:   {}\n\
             \x20 LLM provider:    {}\n\
             \x20 LLM config:      {}\n\
             \x20 LSP:             {}\n\
             \x20 Indexed files:   {}\n\
             \x20 Indexed symbols: {}\n\
             \x20 Dashboard port:  {}",
            self.project_root.display(),
            scope,
            bridge,
            provider_str,
            llm_status,
            lsp_status,
            self.stats.total_files,
            self.stats.total_functions,
            self.dashboard_default_port
        );
        if let Some(intel) = &self.startup_intel {
            if !intel.project_types.is_empty() {
                text.push_str(&format!(
                    "\n  Project type:   {}", intel.project_types.join(", ")
                ));
            }
            if !intel.git_branch.is_empty() {
                text.push_str(&format!("\n  Git branch:     {}", intel.git_branch));
                if intel.git_uncommitted > 0 {
                    text.push_str(&format!(
                        " ({} uncommitted)", intel.git_uncommitted
                    ));
                }
            }
        }
        self.push_message(Message::assistant(text));
    }

    fn show_diagnostics(&mut self, filter: &str) {
        let errors = self.diagnostics_store.error_count();
        let warnings = self.diagnostics_store.warning_count();

        if errors == 0 && warnings == 0 {
            if self.lsp_initialized {
                self.push_message(Message::system("No diagnostics — all clear."));
            } else {
                self.push_message(Message::system(
                    "LSP not started yet. Run /index first to auto-start the language server.",
                ));
            }
            return;
        }

        let filter = filter.trim();
        let severity_filter: Option<&str> = match filter {
            "errors" | "error" | "e" => Some("E"),
            "warnings" | "warning" | "w" => Some("W"),
            _ => None,
        };

        let mut lines = vec![format!(
            "LSP Diagnostics: {} errors, {} warnings",
            errors, warnings
        )];
        lines.push(String::new());

        let store = &self.diagnostics_store;
        if let Some(map) = store.inner_snapshot() {
            let mut files: Vec<_> = map.keys().collect();
            files.sort();
            for file in files.into_iter().take(20) {
                let diags = &map[file];
                let rel = file
                    .strip_prefix(&self.project_root)
                    .unwrap_or(file)
                    .display();
                for d in diags.iter().take(5) {
                    let sev = match d.severity {
                        nala_lsp::DiagSeverity::Error => "E",
                        nala_lsp::DiagSeverity::Warning => "W",
                        nala_lsp::DiagSeverity::Info => "I",
                        nala_lsp::DiagSeverity::Hint => "H",
                    };
                    if let Some(sf) = severity_filter {
                        if sev != sf {
                            continue;
                        }
                    }
                    lines.push(format!(
                        "  [{}] {}:{}:{} — {}",
                        sev,
                        rel,
                        d.line + 1,
                        d.col + 1,
                        d.message,
                    ));
                }
                if diags.len() > 5 {
                    lines.push(format!("  ... and {} more in {}", diags.len() - 5, rel));
                }
            }
        }

        self.push_message(Message::assistant(lines.join("\n")));
    }

    fn team_start(&mut self, objective: String) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.mode = AppMode::Analyzing;
        self.push_message(Message::system(format!(
            "Starting agent team: {}...",
            &objective[..objective.len().min(60)]
        )));
        tokio::spawn(async move {
            if let Err(e) = bridge.team_start(objective).await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    fn team_status(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.team_status().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    fn team_cancel(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.push_message(Message::system("Cancelling team run..."));
        tokio::spawn(async move {
            if let Err(e) = bridge.team_cancel().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    fn handoff_save(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.push_message(Message::system("Saving handoff document..."));
        tokio::spawn(async move {
            if let Err(e) = bridge.handoff_save().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    fn handoff_show(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.handoff_show().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    fn handle_memory_command(&mut self, args: &str) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        let sub: Vec<&str> = args.splitn(2, ' ').collect();
        match sub[0] {
            "" => {
                self.push_message(Message::system("Fetching memory summary..."));
                tokio::spawn(async move {
                    if let Err(e) = bridge.memory_summary().await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
            "sessions" => {
                self.push_message(Message::system("Listing memory sessions..."));
                tokio::spawn(async move {
                    if let Err(e) = bridge.memory_sessions().await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
            "forget" => {
                let target = sub.get(1).copied().unwrap_or("").trim().to_string();
                if target.is_empty() {
                    self.push_message(Message::error("Usage: /memory forget <all|session_id>"));
                    return;
                }
                self.push_message(Message::system(format!("Forgetting: {}...", target)));
                tokio::spawn(async move {
                    if let Err(e) = bridge.memory_forget(target).await {
                        let _ = tx
                            .send(BackgroundEvent::AssistantError(e.to_string()))
                            .await;
                    }
                });
            }
            _ => {
                self.push_message(Message::error(
                    "Usage: /memory | /memory sessions | /memory forget <target>",
                ));
            }
        }
    }

    fn handoff_history(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.handoff_history().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    // ── Undo ───────────────────────────────────────────────────────────

    fn undo_actions(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.push_message(Message::system("Rolling back last action batch..."));
        tokio::spawn(async move {
            if let Err(e) = bridge.undo_actions().await {
                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
            }
        });
    }

    // ── Git commands ───────────────────────────────────────────────────

    fn git_diff(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.push_message(Message::system("Fetching diff..."));
        tokio::spawn(async move {
            if let Err(e) = bridge.git_diff().await {
                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
            }
        });
    }

    fn git_branch(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.push_message(Message::system("Fetching branch info..."));
        tokio::spawn(async move {
            if let Err(e) = bridge.git_branch().await {
                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
            }
        });
    }

    fn git_status(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        self.push_message(Message::system("Fetching git status..."));
        tokio::spawn(async move {
            if let Err(e) = bridge.git_status().await {
                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
            }
        });
    }

    // ── Task commands ──────────────────────────────────────────────────

    fn task_create(&mut self, objective: String) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.task_create(objective).await {
                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
            }
        });
    }

    fn task_status(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.task_status().await {
                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
            }
        });
    }

    fn task_list(&mut self) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.task_list().await {
                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
            }
        });
    }

    fn task_done(&mut self, summary: String) {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system("AI bridge not ready."));
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.task_done(summary).await {
                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
            }
        });
    }

    fn handle_agent_command(&mut self, args: &str) {
        let mut parts = args.splitn(2, ' ');
        let sub = parts.next().unwrap_or("").trim();
        let rest = parts.next().unwrap_or("").trim();

        match sub {
            "" | "help" => {
                self.push_message(Message::assistant(
                    "## /agent — Autonomous Workflow\n\n\
                     **Quick start:** `/agent <objective>` to begin an objective-driven run.\n\n\
                     **Subcommands:**\n\
                     - `/agent <objective>`  — start or resume an objective-driven agent run\n\
                     - `/agent plan [topic]` — create or refresh a plan without executing\n\
                     - `/agent run`          — execute the current plan\n\
                     - `/agent review`       — review current diff and pending changes\n\
                     - `/agent verify`       — run verification analysis\n\
                     - `/agent hotspot`      — quick hotspot triage to find high-value work\n\
                     - `/agent approve`      — approve the pending plan\n\
                     - `/agent reject`       — reject the pending plan\n\
                     - `/agent status`       — show objective, phase, tasks, git state\n\
                     - `/agent stop`         — cancel the active run\n\
                     - `/agent resume`       — resume a paused or blocked run\n\
                     - `/agent mode <level>` — set autonomy: observe, plan, patch, autonomous\n\n\
                     **Workflow:** plan → approve → run → review → verify → done.\n\
                     **Keybindings:** `Ctrl+G` toggles the agent workbench panel.",
                ));
            }
            "plan" => {
                let topic = rest.to_string();
                self.push_message(Message::system(if topic.is_empty() {
                    "Agent: generating plan from current context...".to_string()
                } else {
                    format!("Agent: planning for: {}", topic)
                }));
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_plan(topic).await.map_err(|e| e.to_string())
                });
            }
            "run" => {
                self.push_message(Message::system("Agent: executing plan..."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_run().await.map_err(|e| e.to_string())
                });
            }
            "review" | "review-diff" => {
                self.push_message(Message::system("Agent: reviewing current changes..."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_review().await.map_err(|e| e.to_string())
                });
            }
            "verify" => {
                self.push_message(Message::system("Agent: running verification analysis..."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_verify().await.map_err(|e| e.to_string())
                });
            }
            "hotspot" => {
                self.push_message(Message::system("Agent: running hotspot triage..."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_hotspot().await.map_err(|e| e.to_string())
                });
            }
            "status" => {
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_status().await.map_err(|e| e.to_string())
                });
            }
            "stop" | "cancel" => {
                self.push_message(Message::system("Agent: cancelling active run..."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_stop().await.map_err(|e| e.to_string())
                });
            }
            "resume" => {
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_resume().await.map_err(|e| e.to_string())
                });
            }
            "approve" | "yes" => {
                self.push_message(Message::system("Agent: plan approved, proceeding..."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_approve(true).await.map_err(|e| e.to_string())
                });
            }
            "reject" | "no" => {
                self.push_message(Message::system(
                    "Agent: plan rejected. Revise with /agent plan <feedback>.",
                ));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_approve(false).await.map_err(|e| e.to_string())
                });
            }
            "mode" => {
                let mode = rest.to_string();
                match mode.as_str() {
                    "observe" | "plan" | "patch" | "autonomous" => {
                        self.push_message(Message::system(format!(
                            "Agent: autonomy mode set to {}",
                            mode.to_uppercase()
                        )));
                        self.agent_mode = mode.clone();
                        self.agent_dispatch(move |b, _tx| async move {
                            b.agent_mode(mode).await.map_err(|e| e.to_string())
                        });
                    }
                    _ => {
                        self.push_message(Message::error(
                            "Usage: /agent mode <observe|plan|patch|autonomous>",
                        ));
                    }
                }
            }
            "investigate" | "refactor" | "work" => {
                if rest.is_empty() {
                    self.push_message(Message::error(
                        "Usage: /agent investigate <objective>",
                    ));
                    return;
                }
                let objective = rest.to_string();
                self.push_message(Message::system(format!(
                    "Agent: starting investigation: {}",
                    rest
                )));
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_start(objective).await.map_err(|e| e.to_string())
                });
            }
            _ => {
                let objective = args.trim().to_string();
                if objective.is_empty() {
                    self.push_message(Message::error("Usage: /agent <objective>"));
                } else {
                    self.push_message(Message::system(format!(
                        "Agent: working on \"{}\"",
                        &objective[..objective.len().min(80)]
                    )));
                    self.agent_dispatch(move |b, _tx| async move {
                        b.agent_start(objective).await.map_err(|e| e.to_string())
                    });
                }
            }
        }
    }

    fn agent_dispatch<F, Fut>(&mut self, f: F)
    where
        F: FnOnce(crate::python_bridge::PythonBridge, tokio::sync::mpsc::Sender<BackgroundEvent>) -> Fut + Send + 'static,
        Fut: std::future::Future<Output = Result<(), String>> + Send,
    {
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::system(
                "AI bridge is starting up — please wait a moment.",
            ));
            return;
        };
        let tx = self.bg_tx.clone();
        self.mode = AppMode::Analyzing;
        tokio::spawn(async move {
            if let Err(e) = f(bridge, tx.clone()).await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e))
                    .await;
            }
        });
    }
}

fn dashboard_python_candidates(repo_root: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    if let Ok(explicit) = env::var("NALA_PYTHON") {
        if !explicit.trim().is_empty() {
            candidates.push(PathBuf::from(explicit));
        }
    }

    #[cfg(windows)]
    candidates.push(repo_root.join(".venv").join("Scripts").join("python.exe"));
    #[cfg(not(windows))]
    candidates.push(repo_root.join(".venv").join("bin").join("python"));

    if let Ok(venv) = env::var("VIRTUAL_ENV") {
        #[cfg(windows)]
        candidates.push(PathBuf::from(&venv).join("Scripts").join("python.exe"));
        #[cfg(not(windows))]
        candidates.push(PathBuf::from(&venv).join("bin").join("python"));
    }

    #[cfg(windows)]
    candidates.extend([PathBuf::from("python"), PathBuf::from("py")]);
    #[cfg(not(windows))]
    candidates.extend([PathBuf::from("python3"), PathBuf::from("python")]);

    candidates
}

fn open_dashboard_in_browser(url: &str) {
    #[cfg(windows)]
    let _ = Command::new("cmd")
        .args(["/C", "start", "", url])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();

    #[cfg(target_os = "macos")]
    let _ = Command::new("open")
        .arg(url)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();

    #[cfg(all(unix, not(target_os = "macos")))]
    let _ = Command::new("xdg-open")
        .arg(url)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
}
