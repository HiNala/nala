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
                self.index_phase = Some("Scanning files".to_string());
                self.start_background_scan();
            }
            "/index" => {
                self.push_message(Message::system(
                    "Indexing project (parse + symbols + metrics)...",
                ));
                self.index_progress = Some(0.2);
                self.index_phase = Some("Scanning files".to_string());
                self.start_background_index();
            }
            "/analyze" | "/analyse" => {
                let perspective = parts.get(1).copied().unwrap_or("all").to_string();
                self.run_perspectives(perspective);
            }
            "/model" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                if args.is_empty() {
                    let provider = if self.llm_provider.is_empty() {
                        "none".to_string()
                    } else {
                        self.llm_provider.clone()
                    };
                    let model = if self.llm_model.is_empty() {
                        "not set".to_string()
                    } else {
                        self.llm_model.clone()
                    };
                    let avail = if self.llm_available { "connected" } else { "offline" };
                    self.push_message(Message::assistant(&format!(
                        "## Current Model\n\n\
                         **Provider:** {}\n\
                         **Model:** {}\n\
                         **Status:** {}\n\n\
                         To change, use `/settings`:\n\
                         - `/settings set models.default_provider openai`\n\
                         - `/settings set keys.openai_api_key sk-...`\n\
                         - `/settings setup` — guided configuration\n\n\
                         Or edit `.env` / `.nala/settings.toml` directly.",
                        provider, model, avail,
                    )));
                } else {
                    self.push_message(Message::system(
                        "To switch models, edit LLM_PROVIDER and the matching API key in your `.env` file, then restart Nala.",
                    ));
                }
            }
            "/models" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                match args {
                    "refresh" => {
                        self.push_message(Message::system("Refreshing model registry..."));
                        let Some(bridge) = self.python_bridge.clone() else {
                            self.push_message(Message::system("AI bridge not ready."));
                            return;
                        };
                        let tx = self.bg_tx.clone();
                        tokio::spawn(async move {
                            if let Err(e) = bridge.models_refresh().await {
                                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                            }
                        });
                    }
                    _ => {
                        self.push_message(Message::system("Loading model registry..."));
                        let Some(bridge) = self.python_bridge.clone() else {
                            self.push_message(Message::system("AI bridge not ready."));
                            return;
                        };
                        let tx = self.bg_tx.clone();
                        tokio::spawn(async move {
                            if let Err(e) = bridge.models_list().await {
                                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                            }
                        });
                    }
                }
            }
            "/settings" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.handle_settings_command(args);
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
            // ── Deprecated aliases → silent redirect ───────────────────
            "/act" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                if args.is_empty() {
                    self.push_message(Message::system(
                        "Usage: /act <instruction> — propose file edits with diff preview",
                    ));
                } else {
                    self.push_message(Message::user(format!("/act {}", args)));
                    self.send_action_query(args.to_string());
                }
            }
            "/brain" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                if args.is_empty() {
                    self.push_message(Message::system(
                        "This command has been renamed to `/agent`. Try `/agent <objective>` or `/agent` for help.",
                    ));
                } else {
                    self.handle_agent_command(args);
                }
            }
            "/diff" => {
                self.handle_agent_command("review");
            }
            "/status" => {
                self.handle_agent_command("status");
            }
            "/branch" => {
                self.handle_agent_command("scm");
            }
            "/team" => {
                let args = parts.get(1).copied().unwrap_or("workers");
                let mapped = format!("workers {}", args);
                self.handle_agent_command(mapped.trim());
            }
            "/task" => {
                self.handle_agent_command("status");
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
            "## Nala Commands\n\n",
            "**Ask anything** — just type a question or instruction.\n\n",
            "### Agent\n",
            "  /agent <objective>     — start an autonomous agent run\n",
            "  /agent plan [topic]    — generate a plan\n",
            "  /agent approve / reject — approve or reject the plan\n",
            "  /agent run             — execute the approved plan\n",
            "  /agent review          — review changes and diff\n",
            "  /agent verify          — run project tests/linting\n",
            "  /agent status          — show current run state\n",
            "  /agent stop            — cancel the run\n",
            "  /agent pause / resume  — pause or resume\n",
            "  /agent scm             — git status overview\n",
            "  /agent research <q>    — look up external docs\n",
            "  /agent next            — show suggested next steps\n\n",
            "### Code\n",
            "  /analyze [quick]       — run analysis perspectives\n",
            "  /scope <path>          — focus on a subtree\n",
            "  /read <file>           — show file contents\n",
            "  /tree                  — project file tree\n",
            "  /diag                  — LSP diagnostics\n\n",
            "### Session\n",
            "  /session               — list / create / load sessions\n",
            "  /context               — context window usage\n",
            "  /compact               — free tokens by compacting\n\n",
            "### Memory & Knowledge\n",
            "  /memory                — knowledge base summary\n",
            "  /memory save <fact>    — save a fact to the knowledge base\n",
            "  /memory sessions       — list past session memories\n",
            "  /memory forget <topic> — remove facts matching a topic\n",
            "  /graph                 — Neo4j graph stats\n",
            "  /handoff               — show / save handoff docs\n\n",
            "### Settings\n",
            "  /settings              — show all configuration\n",
            "  /settings set <k> <v>  — change a setting\n",
            "  /settings setup        — guided first-run wizard\n",
            "  /model                 — show current LLM provider/model\n",
            "  /models                — show all available models + routing\n",
            "  /doctor                — environment diagnostics\n\n",
            "### General\n",
            "  /scan / /index         — rescan or reindex project files\n",
            "  /clear                 — clear messages\n",
            "  /help                  — this help\n",
            "  /quit                  — exit\n\n",
            "### Keys\n",
            "  Up/Down                — command history\n",
            "  Shift+Up/Down, PgUp/Dn, Mouse wheel — scroll\n",
            "  Ctrl+B / Ctrl+E       — file / session panels\n",
            "  Ctrl+G                — agent workbench panel\n",
            "  Tab                   — autocomplete commands\n",
            "  Tip: text selection/copy works by default (mouse capture off).\n",
            "       Set `NALA_MOUSE_CAPTURE=1` to enable in-app mouse wheel capture.\n",
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
        Self::walk_tree(root, "", &skip, &mut lines, 0, 300);
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
        if lines.len() >= max_lines || depth > 4 {
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
                let truncated = if line_count > 500 {
                    let shown: String = content.lines().take(500)
                        .collect::<Vec<_>>()
                        .join("\n");
                    format!(
                        "**{}** ({} lines, showing first 500)\n```\n{}\n```\n\n... truncated ({} more lines)",
                        display, line_count, shown, line_count - 500,
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

    /// Launch the agent with a given objective (used by auto-suggest y/n flow).
    pub(crate) fn launch_agent(&mut self, objective: String) {
        self.agent_dispatch(move |b, _tx| async move {
            b.agent_start(objective).await.map_err(|e| e.to_string())
        });
    }

    /// Re-send a query but tell Python to skip the actionable-intent suggestion.
    pub(crate) fn send_llm_query_skip_suggest(&mut self, text: String) {
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
                    if let Err(e) = bridge.query_skip_suggest(text, root).await {
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
            "save" => {
                let fact = sub.get(1).copied().unwrap_or("").trim().to_string();
                if fact.is_empty() {
                    self.push_message(Message::error("Usage: /memory save <fact to remember>"));
                    return;
                }
                self.push_message(Message::system(format!("Saving: {}...", &fact[..fact.len().min(60)])));
                tokio::spawn(async move {
                    if let Err(e) = bridge.memory_save(fact).await {
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
                    "Usage: /memory | /memory sessions | /memory save <fact> | /memory forget <target>",
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

    fn handle_settings_command(&mut self, args: &str) {
        let mut parts = args.splitn(2, ' ');
        let sub = parts.next().unwrap_or("").trim();
        let rest = parts.next().unwrap_or("").trim();

        match sub {
            "" | "show" => {
                self.push_message(Message::system("Loading settings..."));
                let Some(bridge) = self.python_bridge.clone() else {
                    self.push_message(Message::system("AI bridge not ready."));
                    return;
                };
                let tx = self.bg_tx.clone();
                tokio::spawn(async move {
                    if let Err(e) = bridge.settings_show().await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
            "set" => {
                let mut set_parts = rest.splitn(2, ' ');
                let key = set_parts.next().unwrap_or("").trim().to_string();
                let value = set_parts.next().unwrap_or("").trim().to_string();
                if key.is_empty() || value.is_empty() {
                    self.push_message(Message::error(
                        "Usage: /settings set <key> <value>\n\
                         Examples:\n\
                         - /settings set keys.anthropic_api_key sk-ant-...\n\
                         - /settings set models.default_provider openai\n\
                         - /settings set models.routing.plan anthropic/claude-opus-4-6\n\
                         - /settings set agent.autonomy autonomous",
                    ));
                    return;
                }
                self.push_message(Message::system(format!("Setting {} = {}...", key, value)));
                let Some(bridge) = self.python_bridge.clone() else {
                    self.push_message(Message::system("AI bridge not ready."));
                    return;
                };
                let tx = self.bg_tx.clone();
                tokio::spawn(async move {
                    if let Err(e) = bridge.settings_set(key, value).await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
            "setup" => {
                self.push_message(Message::system("Running settings setup..."));
                let Some(bridge) = self.python_bridge.clone() else {
                    self.push_message(Message::system("AI bridge not ready."));
                    return;
                };
                let tx = self.bg_tx.clone();
                tokio::spawn(async move {
                    if let Err(e) = bridge.settings_setup().await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
            "help" => {
                self.push_message(Message::assistant(
                    "## /settings — Configuration\n\n\
                     - `/settings` — show current configuration\n\
                     - `/settings set <key> <value>` — change a setting\n\
                     - `/settings setup` — guided first-run wizard\n\n\
                     **Common keys:**\n\
                     - `keys.anthropic_api_key` / `keys.openai_api_key` / `keys.google_api_key`\n\
                     - `models.default_provider` / `models.default_model`\n\
                     - `models.routing.plan` / `code` / `explore` / `research`\n\
                     - `agent.autonomy` — manual, guided, autonomous\n\
                     - `agent.git.auto_branch` / `agent.git.auto_commit`\n\n\
                     Settings are saved to `.nala/settings.toml`.\n\
                     Environment variables (`.env`) always take precedence.",
                ));
            }
            _ => {
                self.push_message(Message::error(
                    "Usage: /settings [show|set|setup|help]",
                ));
            }
        }
    }

    fn handle_agent_command(&mut self, args: &str) {
        let mut parts = args.splitn(2, ' ');
        let sub = parts.next().unwrap_or("").trim();
        let rest = parts.next().unwrap_or("").trim();

        match sub {
            "" | "help" => {
                self.push_message(Message::assistant(
                    "## /agent — Autonomous Workflow\n\n\
                     **Quick start:** `/agent <objective>` or `/agent objective <goal>`\n\n\
                     **Mission-driven (full orchestration):**\n\
                     - `objective <goal>` — research → plan missions → execute → verify\n\
                     - `missions` — show mission plan status\n\
                     - `approve-missions` / `reject-missions` — accept or revise the plan\n\n\
                     **Core workflow:**\n\
                     - `plan [topic]` — generate a plan\n\
                     - `approve` / `reject` — accept or revise the plan\n\
                     - `run` — execute the plan\n\
                     - `review` — review changes  |  `verify` — run tests\n\
                     - `status` — current state  |  `stop` / `pause` / `resume`\n\n\
                     **More:**\n\
                     - `scm` — git overview  |  `research <q>` — look up docs\n\
                     - `workers` — list workers  |  `next` — suggested steps\n\
                     - `mode <level>` — autonomy: observe, plan, patch, autonomous\n\
                     - `checkpoint` / `checkpoints` / `restore` — save/load state\n\n\
                     **Panel:** `Ctrl+G` toggles agent workbench",
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
            // ── Worker commands (M33) ────────────────────────────────
            "workers" => {
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_workers().await.map_err(|e| e.to_string())
                });
            }
            "attach" => {
                if rest.is_empty() {
                    self.push_message(Message::error("Usage: /agent attach <worker-id>"));
                    return;
                }
                let wid = rest.to_string();
                self.push_message(Message::system(format!("Attaching to worker {}...", rest)));
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_worker_detail(wid).await.map_err(|e| e.to_string())
                });
            }
            "detach" => {
                self.push_message(Message::system("Detached from worker. Back to interpreter."));
            }
            "message" => {
                let mut msg_parts = rest.splitn(2, ' ');
                let wid = msg_parts.next().unwrap_or("").trim().to_string();
                let text = msg_parts.next().unwrap_or("").trim().to_string();
                if wid.is_empty() || text.is_empty() {
                    self.push_message(Message::error(
                        "Usage: /agent message <worker-id> <text>",
                    ));
                    return;
                }
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_worker_message(wid, text).await.map_err(|e| e.to_string())
                });
            }
            "cancel-worker" => {
                if rest.is_empty() {
                    self.push_message(Message::error("Usage: /agent cancel-worker <worker-id>"));
                    return;
                }
                let wid = rest.to_string();
                self.push_message(Message::system(format!("Cancelling worker {}...", rest)));
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_worker_cancel(wid).await.map_err(|e| e.to_string())
                });
            }
            // ── SCM / Git review (M34) ──────────────────────────────
            "scm" => {
                self.push_message(Message::system("Loading SCM overview..."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_scm().await.map_err(|e| e.to_string())
                });
            }
            "compare" => {
                let mut cmp_parts = rest.splitn(2, ' ');
                let base = cmp_parts.next().unwrap_or("main").trim().to_string();
                let head = cmp_parts.next().unwrap_or("HEAD").trim().to_string();
                self.push_message(Message::system(format!(
                    "Comparing {} → {}...", base, head
                )));
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_branch_compare(base, head).await.map_err(|e| e.to_string())
                });
            }
            "blame" => {
                if rest.is_empty() {
                    self.push_message(Message::error("Usage: /agent blame <file> [start] [end]"));
                    return;
                }
                let blame_parts: Vec<&str> = rest.splitn(3, ' ').collect();
                let file = blame_parts[0].to_string();
                let start: u32 = blame_parts.get(1)
                    .and_then(|s| s.parse().ok()).unwrap_or(1);
                let end: u32 = blame_parts.get(2)
                    .and_then(|s| s.parse().ok()).unwrap_or(0);
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_blame(file, start, end).await.map_err(|e| e.to_string())
                });
            }
            "worktree" => {
                let mut wt_parts = rest.splitn(2, ' ');
                let wt_sub = wt_parts.next().unwrap_or("").trim();
                let wt_rest = wt_parts.next().unwrap_or("").trim().to_string();
                match wt_sub {
                    "list" | "" => {
                        self.agent_dispatch(|b, _tx| async move {
                            b.agent_worktree_list().await.map_err(|e| e.to_string())
                        });
                    }
                    "create" => {
                        if wt_rest.is_empty() {
                            self.push_message(Message::error(
                                "Usage: /agent worktree create <label>",
                            ));
                            return;
                        }
                        self.agent_dispatch(move |b, _tx| async move {
                            b.agent_worktree_create(wt_rest).await.map_err(|e| e.to_string())
                        });
                    }
                    "cleanup" | "remove" => {
                        if wt_rest.is_empty() {
                            self.push_message(Message::error(
                                "Usage: /agent worktree cleanup <label>",
                            ));
                            return;
                        }
                        self.agent_dispatch(move |b, _tx| async move {
                            b.agent_worktree_cleanup(wt_rest).await.map_err(|e| e.to_string())
                        });
                    }
                    _ => {
                        self.push_message(Message::error(
                            "Usage: /agent worktree <list|create|cleanup> [label]",
                        ));
                    }
                }
            }
            // ── Research (M35) ──────────────────────────────────────
            "research" => {
                if rest.is_empty() {
                    self.push_message(Message::error("Usage: /agent research <question>"));
                    return;
                }
                let question = rest.to_string();
                self.push_message(Message::system(format!("Researching: {}", rest)));
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_research(question).await.map_err(|e| e.to_string())
                });
            }
            // ── Pause / checkpoint (M36) ────────────────────────────
            "pause" => {
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_pause().await.map_err(|e| e.to_string())
                });
            }
            "checkpoint" => {
                let label = rest.to_string();
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_checkpoint(label).await.map_err(|e| e.to_string())
                });
            }
            "checkpoints" => {
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_checkpoints().await.map_err(|e| e.to_string())
                });
            }
            "restore" => {
                let idx: u32 = rest.parse().unwrap_or(0);
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_restore(idx).await.map_err(|e| e.to_string())
                });
            }
            "next" => {
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_next_steps().await.map_err(|e| e.to_string())
                });
            }
            // ── Mission-driven orchestration (P7-02) ──────────────
            "objective" | "obj" => {
                if rest.is_empty() {
                    self.push_message(Message::error("Usage: /agent objective <goal>"));
                    return;
                }
                let objective = rest.to_string();
                let autonomy = self.agent_mode.clone();
                self.push_message(Message::system(format!(
                    "Agent: starting full orchestration for \"{}\" (mode: {})",
                    &rest[..rest.len().min(60)], autonomy
                )));
                self.agent_dispatch(move |b, _tx| async move {
                    b.agent_objective(objective, autonomy).await.map_err(|e| e.to_string())
                });
            }
            "missions" => {
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_missions_status().await.map_err(|e| e.to_string())
                });
            }
            "approve-missions" => {
                self.push_message(Message::system("Agent: missions approved, executing..."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_approve_missions(true).await.map_err(|e| e.to_string())
                });
            }
            "reject-missions" => {
                self.push_message(Message::system("Agent: missions rejected."));
                self.agent_dispatch(|b, _tx| async move {
                    b.agent_approve_missions(false).await.map_err(|e| e.to_string())
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
