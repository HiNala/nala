//! Application state machine and main event loop.
//!
//! `App` owns all UI state. The event loop polls crossterm for input events
//! and renders the UI at a capped frame rate (~30fps). Heavy work (indexing,
//! analysis) runs on Tokio background tasks and communicates back via channels.
//!
//! Command dispatch lives in `commands.rs`, LSP in `lsp_commands.rs`,
//! and the action confirmation workflow in `actions.rs`.

use anyhow::Result;
use crossterm::event::{
    Event, EventStream, KeyCode, KeyEventKind, KeyModifiers, MouseEventKind,
};
use ratatui::{DefaultTerminal, Frame};
use std::path::{Path, PathBuf};
use std::process::Child;
use std::time::{Duration, Instant};
use tokio::sync::mpsc;
use tokio_stream::StreamExt;

use crate::python_bridge::PythonBridge;
use crate::ui;
use nala_lsp::DiagnosticsStore;

// ── App mode ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AppMode {
    Booting,
    Ready,
    Analyzing,
    Viewing,
    Confirming,
}

impl std::fmt::Display for AppMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Booting => write!(f, "BOOTING"),
            Self::Ready => write!(f, "READY"),
            Self::Analyzing => write!(f, "ANALYZING"),
            Self::Viewing => write!(f, "VIEWING"),
            Self::Confirming => write!(f, "CONFIRM"),
        }
    }
}

// ── Pending action ─────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct PendingAction {
    pub action_id: String,
    pub action_type: String,
    pub description: String,
    pub preview: String,
}

// ── Panel visibility ───────────────────────────────────────────────────────

#[derive(Debug, Clone, Default)]
pub struct PanelState {
    pub file_panel_open: bool,
    pub session_panel_open: bool,
}

// ── Message log ────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MessageKind {
    User,
    Assistant,
    System,
    Error,
}

#[derive(Debug, Clone)]
pub struct Message {
    pub kind: MessageKind,
    pub text: String,
}

impl Message {
    pub fn user(text: impl Into<String>) -> Self {
        Self {
            kind: MessageKind::User,
            text: text.into(),
        }
    }
    pub fn assistant(text: impl Into<String>) -> Self {
        Self {
            kind: MessageKind::Assistant,
            text: text.into(),
        }
    }
    pub fn system(text: impl Into<String>) -> Self {
        Self {
            kind: MessageKind::System,
            text: text.into(),
        }
    }
    pub fn error(text: impl Into<String>) -> Self {
        Self {
            kind: MessageKind::Error,
            text: text.into(),
        }
    }
}

// ── Background event channel ───────────────────────────────────────────────

#[derive(Debug)]
pub enum BackgroundEvent {
    ScanComplete {
        total_files: usize,
        changed_files: usize,
        new_files: usize,
        deleted_count: usize,
        duration_ms: u128,
    },
    IndexComplete {
        indexed_files: usize,
        total_files: usize,
        symbols: usize,
        symbol_payload: Vec<nala_indexer::Symbol>,
    },
    IndexPhase(String),
    IndexError(String),
    AssistantChunk(String),
    AssistantDone,
    AssistantError(String),
    SystemMessage(String),
    SessionReplaced {
        text: String,
    },
    ContextUsageUpdated {
        utilization_pct: f64,
        total_tokens: usize,
        effective_limit: usize,
    },
    BridgeReady {
        has_llm: bool,
        provider: String,
        model: String,
    },
    ProposedAction {
        action_id: String,
        action_type: String,
        description: String,
        preview: String,
    },
    ActionApplied {
        action_id: String,
        success: bool,
        message: String,
        output: String,
    },
    LspStarted {
        server_name: String,
    },
    LspStartFailed(String),
    StartupIntelligence {
        project_types: Vec<String>,
        entry_points: Vec<String>,
        git_branch: String,
        git_uncommitted: usize,
        git_ahead: usize,
        git_behind: usize,
        has_sessions: bool,
        suggestions: Vec<String>,
    },
    AgentStateUpdated {
        run_id: String,
        phase: String,
        objective: String,
        scope: String,
        mode: String,
        task_id: String,
        plan_steps: Vec<String>,
        verification_summary: String,
        workers: Vec<String>,
        choices: Vec<String>,
        checkpoint_count: usize,
        notification_priority: String,
    },
    AgentSuggestion {
        objective: String,
        text: String,
    },
}

// ── App ────────────────────────────────────────────────────────────────────

pub struct App {
    pub project_root: PathBuf,
    pub mode: AppMode,
    pub panels: PanelState,
    pub input: String,
    pub cursor_pos: usize,
    pub history: Vec<String>,
    pub history_idx: Option<usize>,
    pub messages: Vec<Message>,
    pub status_text: String,
    pub index_progress: Option<f64>,
    pub index_phase: Option<String>,
    pub stats: ProjectStats,
    pub splash_start: Instant,
    pub should_quit: bool,
    pub bg_rx: mpsc::Receiver<BackgroundEvent>,
    pub bg_tx: mpsc::Sender<BackgroundEvent>,
    pub streaming_response: Option<String>,
    pub python_bridge: Option<PythonBridge>,
    pub llm_available: bool,
    pub llm_provider: String,
    pub llm_model: String,
    pub pending_actions: Vec<PendingAction>,
    pub apply_all: bool,
    pub analysis_scope: Option<String>,
    pub lsp_initialized: bool,
    pub lsp_server_name: String,
    pub lsp_handle: Option<nala_lsp::LspHandle>,
    pub diagnostics_store: DiagnosticsStore,
    pub context_utilization_pct: f64,
    pub context_total_tokens: usize,
    pub context_effective_limit: usize,
    pub scroll_offset: usize,
    pub scroll_locked_to_bottom: bool,
    pub tab_index: Option<usize>,
    pub saved_input: Option<String>,
    pub last_area_height: u16,
    pub dashboard_process: Option<Child>,
    pub dashboard_port: Option<u16>,
    pub dashboard_default_port: u16,
    pub has_index_snapshot: bool,
    pub last_index_symbol_payload: Vec<nala_indexer::Symbol>,
    pub startup_intel: Option<StartupIntel>,
    // ── Agent workbench state ──
    pub agent_panel_open: bool,
    pub agent_phase: String,
    pub agent_objective: String,
    pub agent_run_id: String,
    pub agent_scope: String,
    pub agent_plan_steps: Vec<String>,
    pub agent_mode: String,
    pub agent_task_id: String,
    pub agent_verification_summary: String,
    pub agent_workers: Vec<String>,
    pub agent_choices: Vec<String>,
    pub agent_checkpoint_count: usize,
    pub agent_notification_priority: String,
    // ── Agent suggestion (auto-detect actionable queries) ──
    pub pending_agent_suggestion: Option<String>,
}

#[derive(Debug, Clone, Default)]
pub struct StartupIntel {
    pub project_types: Vec<String>,
    pub entry_points: Vec<String>,
    pub git_branch: String,
    pub git_uncommitted: usize,
    pub git_ahead: usize,
    pub git_behind: usize,
    pub has_sessions: bool,
    pub suggestions: Vec<String>,
}

#[derive(Debug, Clone, Default)]
pub struct ProjectStats {
    pub total_files: usize,
    pub total_functions: usize,
    pub high_complexity_count: usize,
}

const MAX_MESSAGES: usize = 5_000;

fn load_dashboard_default_port(project_root: &Path) -> u16 {
    const DEFAULT_PORT: u16 = 3000;

    if let Ok(raw) = std::env::var("DASHBOARD_PORT") {
        if let Ok(port) = raw.trim().parse::<u16>() {
            return port;
        }
    }

    let env_path = project_root.join(".env");
    let Ok(contents) = std::fs::read_to_string(env_path) else {
        return DEFAULT_PORT;
    };

    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((key, value)) = trimmed.split_once('=') else {
            continue;
        };
        if key.trim() != "DASHBOARD_PORT" {
            continue;
        }
        let value = value.trim().trim_matches('"').trim_matches('\'');
        if let Ok(port) = value.parse::<u16>() {
            return port;
        }
    }

    DEFAULT_PORT
}

fn assistant_error_message(error: &str) -> String {
    let trimmed = error.trim();
    let lower = trimmed.to_ascii_lowercase();
    let is_auth_issue = [
        "api key",
        "authentication",
        "unauthorized",
        "invalid_api_key",
        "invalid api key",
        "missing api key",
        "incorrect api key",
        "forbidden",
        "401",
        "403",
    ]
    .iter()
    .any(|needle| lower.contains(needle));

    if is_auth_issue {
        format!(
            "AI request failed: {}. Check the active provider and API key in your project .env, then retry.",
            trimmed
        )
    } else {
        format!("AI request failed: {}", trimmed)
    }
}

impl App {
    pub fn new(project_root: &Path) -> Result<Self> {
        let (tx, rx) = mpsc::channel(256);
        let canonical_root = project_root
            .canonicalize()
            .unwrap_or_else(|_| project_root.to_path_buf());
        let dashboard_default_port = load_dashboard_default_port(&canonical_root);
        Ok(Self {
            project_root: canonical_root,
            mode: AppMode::Booting,
            panels: PanelState::default(),
            input: String::new(),
            cursor_pos: 0,
            history: Vec::new(),
            history_idx: None,
            messages: Vec::new(),
            status_text: "Initializing...".to_string(),
            index_progress: None,
            index_phase: None,
            stats: ProjectStats::default(),
            splash_start: Instant::now(),
            should_quit: false,
            bg_rx: rx,
            bg_tx: tx,
            streaming_response: None,
            python_bridge: None,
            llm_available: false,
            llm_provider: String::new(),
            llm_model: String::new(),
            pending_actions: Vec::new(),
            apply_all: false,
            analysis_scope: None,
            lsp_initialized: false,
            lsp_server_name: String::new(),
            lsp_handle: None,
            diagnostics_store: DiagnosticsStore::new(),
            context_utilization_pct: 0.0,
            context_total_tokens: 0,
            context_effective_limit: 0,
            scroll_offset: 0,
            scroll_locked_to_bottom: true,
            tab_index: None,
            saved_input: None,
            last_area_height: 30,
            dashboard_process: None,
            dashboard_port: None,
            dashboard_default_port,
            has_index_snapshot: false,
            last_index_symbol_payload: Vec::new(),
            startup_intel: None,
            agent_panel_open: false,
            agent_phase: String::new(),
            agent_objective: String::new(),
            agent_run_id: String::new(),
            agent_scope: String::new(),
            agent_plan_steps: Vec::new(),
            agent_mode: "plan".to_string(),
            agent_task_id: String::new(),
            agent_verification_summary: String::new(),
            agent_workers: Vec::new(),
            agent_choices: Vec::new(),
            agent_checkpoint_count: 0,
            agent_notification_priority: "quiet".to_string(),
            pending_agent_suggestion: None,
        })
    }

    pub fn push_message(&mut self, msg: Message) {
        self.messages.push(msg);
        if self.messages.len() > MAX_MESSAGES {
            let drain = self.messages.len() - MAX_MESSAGES;
            self.messages.drain(0..drain);
        }
        if self.scroll_locked_to_bottom {
            self.scroll_offset = 0;
        }
    }

    pub(crate) fn refresh_context_usage(&self) {
        let Some(bridge) = self.python_bridge.clone() else {
            return;
        };
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = bridge.context_usage_silent().await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
    }

    // ── Main loop ──────────────────────────────────────────────────────────

    pub async fn run(&mut self) -> Result<()> {
        let mut terminal = ratatui::init();
        // Default is copy/select friendly: mouse capture OFF.
        // Set NALA_MOUSE_CAPTURE=1 if you prefer in-app mouse wheel capture.
        let mouse_capture_enabled = std::env::var("NALA_MOUSE_CAPTURE")
            .map(|v| matches!(v.trim(), "1" | "true" | "TRUE" | "yes" | "on"))
            .unwrap_or(false);
        if mouse_capture_enabled {
            crossterm::execute!(
                std::io::stdout(),
                crossterm::event::EnableMouseCapture,
                crossterm::event::EnableBracketedPaste
            )?;
        } else {
            crossterm::execute!(std::io::stdout(), crossterm::event::EnableBracketedPaste)?;
        }
        self.start_python_bridge().await;
        let result = self.event_loop(&mut terminal).await;
        self.cleanup_dashboard_process();
        if mouse_capture_enabled {
            crossterm::execute!(
                std::io::stdout(),
                crossterm::event::DisableBracketedPaste,
                crossterm::event::DisableMouseCapture
            )?;
        } else {
            crossterm::execute!(std::io::stdout(), crossterm::event::DisableBracketedPaste)?;
        }
        ratatui::restore();
        result
    }

    async fn event_loop(&mut self, terminal: &mut DefaultTerminal) -> Result<()> {
        let tick = Duration::from_millis(33);
        let mut reader = EventStream::new();
        let mut last_render = Instant::now();

        self.index_progress = Some(0.1);
        self.index_phase = Some("Scanning project files".to_string());
        self.start_background_index();

        loop {
            if last_render.elapsed() >= tick {
                terminal.draw(|f| self.render(f))?;
                last_render = Instant::now();
            }

            if self.mode == AppMode::Booting && self.python_bridge.is_some() {
                self.mode = AppMode::Ready;
            }

            if self.should_quit {
                break;
            }

            tokio::select! {
                Some(Ok(event)) = reader.next() => {
                    self.handle_event(event);
                }
                Some(bg) = self.bg_rx.recv() => {
                    self.handle_background_event(bg);
                }
                _ = tokio::time::sleep(tick) => {}
            }
        }

        Ok(())
    }

    // ── Rendering ──────────────────────────────────────────────────────────

    fn render(&self, frame: &mut Frame) {
        ui::layout::render(frame, self);
    }

    // ── Event handling ─────────────────────────────────────────────────────

    fn handle_event(&mut self, event: Event) {
        match event {
            Event::Key(key) => self.handle_key(key),
            Event::Mouse(mouse) => self.handle_mouse(mouse),
            Event::Paste(text) => self.handle_paste(text),
            Event::Resize(_, h) => {
                self.last_area_height = h;
            }
            _ => {}
        }
    }

    fn handle_paste(&mut self, text: String) {
        let clean = text.replace('\r', "").replace('\n', " ");
        self.input.insert_str(self.cursor_pos, &clean);
        self.cursor_pos += clean.len();
        self.history_idx = None;
        self.tab_index = None;
    }

    fn handle_mouse(&mut self, mouse: crossterm::event::MouseEvent) {
        match mouse.kind {
            MouseEventKind::ScrollUp => {
                self.scroll_offset = self.scroll_offset.saturating_add(3);
                self.scroll_locked_to_bottom = false;
            }
            MouseEventKind::ScrollDown => {
                if self.scroll_offset > 0 {
                    self.scroll_offset = self.scroll_offset.saturating_sub(3);
                }
                if self.scroll_offset == 0 {
                    self.scroll_locked_to_bottom = true;
                }
            }
            _ => {}
        }
    }

    fn handle_key(&mut self, key: crossterm::event::KeyEvent) {
        use KeyCode::*;

        if key.kind != KeyEventKind::Press {
            return;
        }

        if key.modifiers.contains(KeyModifiers::SHIFT) {
            match key.code {
                Up => {
                    self.scroll_offset = self.scroll_offset.saturating_add(3);
                    self.scroll_locked_to_bottom = false;
                    return;
                }
                Down => {
                    self.scroll_offset = self.scroll_offset.saturating_sub(3);
                    if self.scroll_offset == 0 {
                        self.scroll_locked_to_bottom = true;
                    }
                    return;
                }
                _ => {}
            }
        }

        if key.modifiers.contains(KeyModifiers::CONTROL) {
            match key.code {
                Char('c') | Char('q') => {
                    self.should_quit = true;
                    return;
                }
                Char('b') => {
                    self.panels.file_panel_open = !self.panels.file_panel_open;
                    return;
                }
                Char('e') => {
                    self.panels.session_panel_open = !self.panels.session_panel_open;
                    return;
                }
                Char('g') => {
                    self.agent_panel_open = !self.agent_panel_open;
                    return;
                }
                Left => {
                    self.cursor_pos = word_boundary_left(&self.input, self.cursor_pos);
                    return;
                }
                Right => {
                    self.cursor_pos = word_boundary_right(&self.input, self.cursor_pos);
                    return;
                }
                Char('w') => {
                    let left = word_boundary_left(&self.input, self.cursor_pos);
                    self.input.drain(left..self.cursor_pos);
                    self.cursor_pos = left;
                    return;
                }
                _ => {}
            }
        }

        if self.mode == AppMode::Booting {
            return;
        }

        if self.mode == AppMode::Confirming {
            self.handle_confirm_key(key.code);
            return;
        }

        match key.code {
            Enter => self.submit_input(),
            Tab => self.cycle_tab_completion(),
            Char(c) => {
                self.history_idx = None;
                self.tab_index = None;
                self.input.insert(self.cursor_pos, c);
                self.cursor_pos += c.len_utf8();
            }
            Backspace => {
                self.tab_index = None;
                if self.cursor_pos > 0 {
                    let prev = self.input[..self.cursor_pos]
                        .char_indices()
                        .next_back()
                        .map(|(i, _)| i)
                        .unwrap_or(0);
                    self.input.remove(prev);
                    self.cursor_pos = prev;
                }
            }
            Delete => {
                self.tab_index = None;
                if self.cursor_pos < self.input.len()
                    && self.input.is_char_boundary(self.cursor_pos)
                {
                    self.input.remove(self.cursor_pos);
                }
            }
            Left => {
                if self.cursor_pos > 0 {
                    self.cursor_pos = self.input[..self.cursor_pos]
                        .char_indices()
                        .next_back()
                        .map(|(i, _)| i)
                        .unwrap_or(0);
                }
            }
            Right => {
                if self.cursor_pos < self.input.len() {
                    self.cursor_pos = self.input[self.cursor_pos..]
                        .char_indices()
                        .nth(1)
                        .map(|(i, _)| self.cursor_pos + i)
                        .unwrap_or(self.input.len());
                }
            }
            Home => self.cursor_pos = 0,
            End => self.cursor_pos = self.input.len(),
            PageUp => {
                self.scroll_offset = self.scroll_offset.saturating_add(10);
                self.scroll_locked_to_bottom = false;
            }
            PageDown => {
                self.scroll_offset = self.scroll_offset.saturating_sub(10);
                if self.scroll_offset == 0 {
                    self.scroll_locked_to_bottom = true;
                }
            }
            Up => self.history_up(),
            Down => self.history_down(),
            Esc => {
                if self.mode == AppMode::Analyzing {
                    self.mode = AppMode::Ready;
                    self.streaming_response = None;
                    self.push_message(Message {
                        kind: MessageKind::System,
                        text: "Request cancelled.".to_string(),
                    });
                } else {
                    self.input.clear();
                    self.cursor_pos = 0;
                    self.history_idx = None;
                    self.saved_input = None;
                    self.tab_index = None;
                }
            }
            _ => {}
        }
    }

    fn history_up(&mut self) {
        if self.history.is_empty() {
            return;
        }
        if self.history_idx.is_none() {
            self.saved_input = Some(self.input.clone());
        }
        let new_idx = match self.history_idx {
            None => self.history.len() - 1,
            Some(0) => 0,
            Some(i) => i - 1,
        };
        self.history_idx = Some(new_idx);
        self.input = self.history[new_idx].clone();
        self.cursor_pos = self.input.len();
    }

    fn history_down(&mut self) {
        match self.history_idx {
            None => {}
            Some(i) if i + 1 >= self.history.len() => {
                self.history_idx = None;
                self.input = self.saved_input.take().unwrap_or_default();
                self.cursor_pos = self.input.len();
            }
            Some(i) => {
                self.history_idx = Some(i + 1);
                self.input = self.history[i + 1].clone();
                self.cursor_pos = self.input.len();
            }
        }
    }

    fn submit_input(&mut self) {
        let input = self.input.trim().to_string();
        if input.is_empty() {
            return;
        }
        self.history.push(input.clone());
        self.history_idx = None;
        self.saved_input = None;
        self.input.clear();
        self.cursor_pos = 0;

        self.push_message(Message::user(&input));
        self.dispatch_command(input);
    }

    fn dispatch_command(&mut self, input: String) {
        // Check for pending agent suggestion (y/n response)
        if let Some(objective) = self.pending_agent_suggestion.take() {
            let lower = input.trim().to_lowercase();
            if lower == "y" || lower == "yes" {
                self.push_message(Message::system("Launching agent..."));
                self.launch_agent(objective);
                return;
            }
            // "n", "no", or anything else — send as regular query (skip suggestion)
            if lower == "n" || lower == "no" {
                self.push_message(Message::system(
                    "Skipped. Answering with context only.",
                ));
                self.send_llm_query_skip_suggest(objective);
                return;
            }
            // User typed something else entirely — process it as a new command
        }

        if input.starts_with('/') {
            self.handle_slash_command(&input);
        } else {
            self.send_llm_query(input);
        }
    }

    // ── Background tasks ───────────────────────────────────────────────────

    pub(crate) fn start_background_scan(&self) {
        let root = self.project_root.clone();
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            let result =
                tokio::task::spawn_blocking(move || nala_indexer::scan_project(&root)).await;

            match result {
                Ok(Ok(scan)) => {
                    let _ = tx
                        .send(BackgroundEvent::ScanComplete {
                            total_files: scan.total_files,
                            changed_files: scan.changed_files.len(),
                            new_files: scan.new_files.len(),
                            deleted_count: scan.deleted_count,
                            duration_ms: scan.scan_duration.as_millis(),
                        })
                        .await;
                }
                Ok(Err(e)) => {
                    let _ = tx.send(BackgroundEvent::IndexError(e.to_string())).await;
                }
                Err(e) => {
                    let _ = tx
                        .send(BackgroundEvent::IndexError(format!(
                            "Scan task panicked: {}",
                            e
                        )))
                        .await;
                }
            }
        });
    }

    pub(crate) fn start_background_index(&self) {
        let root = self.project_root.clone();
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            let _ = tx.send(BackgroundEvent::IndexPhase("Scanning files".to_string())).await;

            let phase_tx = tx.clone();
            let result = tokio::task::spawn_blocking(move || {
                let scan = nala_indexer::scan_project(&root)?;
                let n_to_parse = if scan.changed_files.is_empty() {
                    scan.all_files.len()
                } else {
                    scan.changed_files.len()
                };
                let _ = phase_tx.blocking_send(BackgroundEvent::IndexPhase(
                    format!("Parsing {} files", n_to_parse),
                ));
                nala_indexer::index_with_scan(scan, &root)
            })
            .await;

            match result {
                Ok(Ok(index_result)) => {
                    let _ = tx
                        .send(BackgroundEvent::IndexComplete {
                            indexed_files: index_result.indexed_files,
                            total_files: index_result.scan_result.total_files,
                            symbols: index_result.total_symbols,
                            symbol_payload: index_result.symbols,
                        })
                        .await;
                }
                Ok(Err(e)) => {
                    let _ = tx.send(BackgroundEvent::IndexError(e.to_string())).await;
                }
                Err(e) => {
                    let _ = tx
                        .send(BackgroundEvent::IndexError(format!(
                            "Index task panicked: {}",
                            e
                        )))
                        .await;
                }
            }
        });
    }

    fn handle_background_event(&mut self, event: BackgroundEvent) {
        match event {
            BackgroundEvent::ScanComplete {
                total_files,
                changed_files,
                new_files,
                deleted_count,
                duration_ms,
            } => {
                self.index_progress = None;
                self.index_phase = None;
                crate::ui::file_panel::invalidate_cache();
                self.stats.total_files = total_files;
                self.push_message(Message::system(format!(
                    "Scan complete in {}ms: {} files ({} changed, {} new, {} deleted)",
                    duration_ms, total_files, changed_files, new_files, deleted_count
                )));
                if self.mode == AppMode::Analyzing || self.mode == AppMode::Booting {
                    self.mode = AppMode::Ready;
                }
            }
            BackgroundEvent::IndexComplete {
                indexed_files,
                total_files,
                symbols,
                symbol_payload,
            } => {
                self.index_progress = None;
                self.index_phase = None;
                crate::ui::file_panel::invalidate_cache();
                self.stats.total_files = total_files;
                self.stats.total_functions = symbols;
                self.has_index_snapshot = true;
                self.last_index_symbol_payload = symbol_payload.clone();
                self.status_text = format!(
                    "{} files in project • {} files reindexed • {} symbols",
                    total_files, indexed_files, symbols
                );
                self.push_message(Message::system(format!(
                    "Index complete: {} files in project, {} files reindexed, {} symbols.",
                    total_files, indexed_files, symbols
                )));

                if let Some(bridge) = &self.python_bridge {
                    let bridge = bridge.clone();
                    let tx = self.bg_tx.clone();
                    tokio::spawn(async move {
                        if let Err(e) = bridge
                            .index_context(total_files, symbols, symbol_payload)
                            .await
                        {
                            let _ = tx
                                .send(BackgroundEvent::AssistantError(e.to_string()))
                                .await;
                        }
                    });
                }

                if !self.lsp_initialized {
                    self.start_lsp_background();
                }
            }
            BackgroundEvent::IndexPhase(phase) => {
                self.index_phase = Some(phase);
            }
            BackgroundEvent::IndexError(e) => {
                self.index_progress = None;
                self.index_phase = None;
                self.push_message(Message::error(format!(
                    "Indexing failed: {}. Try running /scan first or check file permissions.",
                    e
                )));
            }
            BackgroundEvent::AssistantChunk(chunk) => {
                if let Some(ref mut resp) = self.streaming_response {
                    resp.push_str(&chunk);
                } else {
                    self.streaming_response = Some(chunk);
                }
            }
            BackgroundEvent::AssistantDone => {
                self.mode = AppMode::Ready;
                if let Some(text) = self.streaming_response.take() {
                    self.push_message(Message::assistant(text));
                }
                self.refresh_context_usage();
            }
            BackgroundEvent::AssistantError(e) => {
                self.mode = AppMode::Ready;
                if let Some(partial) = self.streaming_response.take() {
                    if !partial.is_empty() {
                        self.push_message(Message::assistant(partial));
                    }
                }
                self.push_message(Message::error(assistant_error_message(&e)));
            }
            BackgroundEvent::SystemMessage(text) => {
                self.push_message(Message::system(text));
            }
            BackgroundEvent::SessionReplaced { text } => {
                self.mode = AppMode::Ready;
                self.streaming_response = None;
                self.messages.clear();
                self.pending_actions.clear();
                self.apply_all = false;
                self.push_message(Message::system(text));
                self.refresh_context_usage();
            }
            BackgroundEvent::ContextUsageUpdated {
                utilization_pct,
                total_tokens,
                effective_limit,
            } => {
                self.context_utilization_pct = utilization_pct;
                self.context_total_tokens = total_tokens;
                self.context_effective_limit = effective_limit;
            }
            BackgroundEvent::BridgeReady {
                has_llm,
                provider,
                model,
            } => {
                self.llm_available = has_llm;
                self.llm_provider = provider;
                self.llm_model = model;
                if has_llm {
                    self.status_text = "AI ready".to_string();
                } else {
                    self.status_text = "AI offline — add API key to .env".to_string();
                }
                if self.has_index_snapshot {
                    if let Some(bridge) = &self.python_bridge {
                        let bridge = bridge.clone();
                        let total_files = self.stats.total_files;
                        let total_symbols = self.stats.total_functions;
                        let symbol_payload = self.last_index_symbol_payload.clone();
                        tokio::spawn(async move {
                            let _ = bridge
                                .index_context(total_files, total_symbols, symbol_payload)
                                .await;
                        });
                    }
                }
                self.refresh_context_usage();
            }
            BackgroundEvent::ProposedAction {
                action_id,
                action_type,
                description,
                preview,
            } => {
                self.pending_actions.push(PendingAction {
                    action_id,
                    action_type,
                    description,
                    preview,
                });
                if self.mode != AppMode::Confirming {
                    self.show_next_pending_action();
                }
            }
            BackgroundEvent::ActionApplied {
                action_id,
                success,
                message,
                output,
            } => {
                self.pending_actions.retain(|a| a.action_id != action_id);
                if success {
                    let mut text = format!("Applied: {}", message);
                    if !output.is_empty() {
                        text.push('\n');
                        text.push_str(&output);
                    }
                    self.push_message(Message::system(text));
                } else {
                    self.push_message(Message::error(format!(
                        "Action failed: {}. The action has been discarded.",
                        message
                    )));
                }
                self.show_next_pending_action();
            }
            BackgroundEvent::LspStarted { server_name } => {
                self.lsp_initialized = true;
                self.lsp_server_name = server_name.clone();
                self.push_message(Message::system(format!(
                    "LSP: {} started (diagnostics active)",
                    server_name
                )));
            }
            BackgroundEvent::LspStartFailed(reason) => {
                self.push_message(Message::system(format!("LSP: not available — {}", reason)));
            }
            BackgroundEvent::StartupIntelligence {
                project_types,
                entry_points,
                git_branch,
                git_uncommitted,
                git_ahead,
                git_behind,
                has_sessions,
                suggestions,
            } => {
                self.startup_intel = Some(StartupIntel {
                    project_types,
                    entry_points,
                    git_branch,
                    git_uncommitted,
                    git_ahead,
                    git_behind,
                    has_sessions,
                    suggestions,
                });
            }
            BackgroundEvent::AgentStateUpdated {
                run_id,
                phase,
                objective,
                scope,
                mode,
                task_id,
                plan_steps,
                verification_summary,
                workers,
                choices,
                checkpoint_count,
                notification_priority,
            } => {
                self.agent_run_id = run_id;
                self.agent_phase = phase.clone();
                self.agent_objective = objective;
                self.agent_scope = scope;
                self.agent_mode = mode;
                self.agent_task_id = task_id;
                self.agent_plan_steps = plan_steps;
                self.agent_verification_summary = verification_summary;
                self.agent_workers = workers;
                self.agent_choices = choices;
                self.agent_checkpoint_count = checkpoint_count;
                self.agent_notification_priority = notification_priority;
                if phase == "idle" || phase == "done" || phase == "cancelled" {
                    if self.agent_panel_open && phase != "idle" {
                        // keep panel open so user sees final state
                    }
                } else if !self.agent_panel_open {
                    self.agent_panel_open = true;
                }
            }
            BackgroundEvent::AgentSuggestion { objective, text } => {
                self.mode = AppMode::Ready;
                if let Some(partial) = self.streaming_response.take() {
                    if !partial.is_empty() {
                        self.push_message(Message::assistant(partial));
                    }
                }
                self.pending_agent_suggestion = Some(objective);
                self.push_message(Message::system(text));
            }
        }
    }

    pub(crate) fn start_lsp_background(&mut self) {
        let handle = nala_lsp::LspHandle::new(&self.project_root, self.diagnostics_store.clone());
        self.lsp_handle = Some(handle.clone());

        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            let server_name = handle.server_name().await;
            if server_name == "none" {
                let _ = tx
                    .send(BackgroundEvent::LspStartFailed(
                        "no supported language server found".into(),
                    ))
                    .await;
                return;
            }
            if let Err(e) = handle.initialize().await {
                let _ = tx
                    .send(BackgroundEvent::LspStartFailed(e.to_string()))
                    .await;
                return;
            }
            if !handle.is_initialized().await {
                let _ = tx
                    .send(BackgroundEvent::LspStartFailed(format!(
                        "{} failed to initialize",
                        server_name
                    )))
                    .await;
                return;
            }
            let _ = tx.send(BackgroundEvent::LspStarted { server_name }).await;

            let _ = tx.closed().await;
            let _ = handle.shutdown().await;
        });
    }

    // ── Python bridge ──────────────────────────────────────────────────────

    async fn start_python_bridge(&mut self) {
        let root = self.project_root.clone();
        let bg_tx = self.bg_tx.clone();

        match crate::python_bridge::spawn(&root, bg_tx.clone()).await {
            Ok(bridge) => {
                self.python_bridge = Some(bridge);
            }
            Err(e) => {
                self.push_message(Message::system(format!(
                    "Python bridge unavailable: {}. Natural language queries disabled.",
                    e
                )));
                if self.mode == AppMode::Booting {
                    self.mode = AppMode::Ready;
                }
            }
        }
    }

    fn cleanup_dashboard_process(&mut self) {
        if let Some(mut child) = self.dashboard_process.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.dashboard_port = None;
    }
}

// ── Slash-command names for tab completion ──────────────────────────────────

pub const SLASH_COMMANDS: &[&str] = &[
    // ── Agent workflow ──
    "/agent",
    "/agent plan",
    "/agent run",
    "/agent review",
    "/agent verify",
    "/agent approve",
    "/agent reject",
    "/agent status",
    "/agent stop",
    "/agent pause",
    "/agent resume",
    "/agent scm",
    "/agent research",
    "/agent next",
    "/agent workers",
    "/agent mode",
    "/agent checkpoint",
    "/agent checkpoints",
    "/agent restore",
    // ── Code ──
    "/analyze",
    "/analyze quick",
    "/scope",
    "/read",
    "/tree",
    "/diag",
    // ── Session ──
    "/session",
    "/session new",
    "/session load",
    "/context",
    "/compact",
    "/agent objective",
    "/agent missions",
    "/agent approve-missions",
    // ── Memory & Knowledge ──
    "/memory",
    "/memory save",
    "/memory sessions",
    "/memory forget",
    "/graph",
    "/handoff",
    "/handoff save",
    "/handoff history",
    // ── Settings ──
    "/settings",
    "/settings set",
    "/settings setup",
    "/model",
    "/models",
    "/models refresh",
    "/doctor",
    // ── General ──
    "/scan",
    "/index",
    "/clear",
    "/help",
    "/quit",
];

impl App {
    fn cycle_tab_completion(&mut self) {
        if !self.input.starts_with('/') {
            return;
        }
        let prefix = self.input.clone();
        let matches: Vec<&&str> = SLASH_COMMANDS
            .iter()
            .filter(|cmd| cmd.starts_with(&prefix) && **cmd != prefix.as_str())
            .collect();
        if matches.is_empty() {
            return;
        }
        let idx = match self.tab_index {
            Some(i) => (i + 1) % matches.len(),
            None => 0,
        };
        self.tab_index = Some(idx);
        self.input = matches[idx].to_string();
        self.cursor_pos = self.input.len();
    }
}

/// Return the first matching command for the current input prefix (for ghost hint).
pub fn tab_hint(input: &str) -> Option<&'static str> {
    if !input.starts_with('/') || input.len() < 2 {
        return None;
    }
    SLASH_COMMANDS
        .iter()
        .find(|cmd| cmd.starts_with(input) && **cmd != input)
        .copied()
}

// ── Word boundary helpers for Ctrl+Left/Right ──────────────────────────────

fn word_boundary_left(text: &str, pos: usize) -> usize {
    if pos == 0 {
        return 0;
    }
    let bytes = text.as_bytes();
    let mut i = pos - 1;
    while i > 0 && bytes[i].is_ascii_whitespace() {
        i -= 1;
    }
    while i > 0 && !bytes[i - 1].is_ascii_whitespace() {
        i -= 1;
    }
    i
}

fn word_boundary_right(text: &str, pos: usize) -> usize {
    let len = text.len();
    if pos >= len {
        return len;
    }
    let bytes = text.as_bytes();
    let mut i = pos;
    while i < len && !bytes[i].is_ascii_whitespace() {
        i += 1;
    }
    while i < len && bytes[i].is_ascii_whitespace() {
        i += 1;
    }
    i
}
