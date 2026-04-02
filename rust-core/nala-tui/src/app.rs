//! Application state machine and main event loop.
//!
//! `App` owns all UI state. The event loop polls crossterm for input events
//! and renders the UI at a capped frame rate (~30fps). Heavy work (indexing,
//! analysis) runs on Tokio background tasks and communicates back via channels.
//!
//! Command dispatch lives in `commands.rs`, LSP in `lsp_commands.rs`,
//! and the action confirmation workflow in `actions.rs`.

use anyhow::Result;
use crossterm::event::{Event, EventStream, KeyCode, KeyModifiers};
use ratatui::{DefaultTerminal, Frame};
use std::path::{Path, PathBuf};
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
    Command,
    Analyzing,
    Viewing,
    Confirming,
}

impl std::fmt::Display for AppMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Booting => write!(f, "BOOTING"),
            Self::Ready => write!(f, "READY"),
            Self::Command => write!(f, "COMMAND"),
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
        Self { kind: MessageKind::User, text: text.into() }
    }
    pub fn assistant(text: impl Into<String>) -> Self {
        Self { kind: MessageKind::Assistant, text: text.into() }
    }
    pub fn system(text: impl Into<String>) -> Self {
        Self { kind: MessageKind::System, text: text.into() }
    }
    pub fn error(text: impl Into<String>) -> Self {
        Self { kind: MessageKind::Error, text: text.into() }
    }
}

// ── Background event channel ───────────────────────────────────────────────

#[derive(Debug)]
pub enum BackgroundEvent {
    IndexComplete {
        indexed_files: usize,
        total_files: usize,
        symbols: usize,
        symbol_payload: Vec<nala_indexer::Symbol>,
    },
    IndexError(String),
    AssistantChunk(String),
    AssistantDone,
    AssistantError(String),
    BridgeReady { has_llm: bool },
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
    pub stats: ProjectStats,
    pub splash_start: Instant,
    pub should_quit: bool,
    pub bg_rx: mpsc::Receiver<BackgroundEvent>,
    pub bg_tx: mpsc::Sender<BackgroundEvent>,
    pub streaming_response: Option<String>,
    pub python_bridge: Option<PythonBridge>,
    pub llm_available: bool,
    pub pending_actions: Vec<PendingAction>,
    pub apply_all: bool,
    pub analysis_scope: Option<String>,
    pub lsp_initialized: bool,
    pub diagnostics_store: DiagnosticsStore,
}

#[derive(Debug, Clone, Default)]
pub struct ProjectStats {
    pub total_files: usize,
    pub total_functions: usize,
    pub high_complexity_count: usize,
}

const MAX_MESSAGES: usize = 1_000;

impl App {
    pub fn new(project_root: &Path) -> Result<Self> {
        let (tx, rx) = mpsc::channel(64);
        Ok(Self {
            project_root: project_root.to_path_buf(),
            mode: AppMode::Booting,
            panels: PanelState::default(),
            input: String::new(),
            cursor_pos: 0,
            history: Vec::new(),
            history_idx: None,
            messages: vec![Message::system(
                "Welcome to Nala. Type a question or /help for commands.",
            )],
            status_text: "Initializing...".to_string(),
            index_progress: None,
            stats: ProjectStats::default(),
            splash_start: Instant::now(),
            should_quit: false,
            bg_rx: rx,
            bg_tx: tx,
            streaming_response: None,
            python_bridge: None,
            llm_available: false,
            pending_actions: Vec::new(),
            apply_all: false,
            analysis_scope: None,
            lsp_initialized: false,
            diagnostics_store: DiagnosticsStore::new(),
        })
    }

    pub fn push_message(&mut self, msg: Message) {
        self.messages.push(msg);
        if self.messages.len() > MAX_MESSAGES {
            let drain = self.messages.len() - MAX_MESSAGES;
            self.messages.drain(0..drain);
        }
    }

    // ── Main loop ──────────────────────────────────────────────────────────

    pub async fn run(&mut self) -> Result<()> {
        let mut terminal = ratatui::init();
        self.start_python_bridge().await;
        let result = self.event_loop(&mut terminal).await;
        ratatui::restore();
        result
    }

    async fn event_loop(&mut self, terminal: &mut DefaultTerminal) -> Result<()> {
        let tick = Duration::from_millis(33);
        let mut reader = EventStream::new();
        let mut last_render = Instant::now();

        self.index_progress = Some(0.1);
        self.start_background_index();

        loop {
            if last_render.elapsed() >= tick {
                terminal.draw(|f| self.render(f))?;
                last_render = Instant::now();
            }

            if self.mode == AppMode::Booting
                && self.splash_start.elapsed() > Duration::from_millis(1500)
            {
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
        if self.mode == AppMode::Booting {
            ui::splash::render(frame, self);
        } else {
            ui::layout::render(frame, self);
        }
    }

    // ── Event handling ─────────────────────────────────────────────────────

    fn handle_event(&mut self, event: Event) {
        match event {
            Event::Key(key) => self.handle_key(key),
            Event::Resize(_, _) => {}
            Event::Mouse(_) => {}
            _ => {}
        }
    }

    fn handle_key(&mut self, key: crossterm::event::KeyEvent) {
        use KeyCode::*;

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
            Char(c) => {
                self.history_idx = None;
                self.input.insert(self.cursor_pos, c);
                self.cursor_pos += c.len_utf8();
            }
            Backspace => {
                if self.cursor_pos > 0 {
                    let prev = self.cursor_pos - 1;
                    self.input.remove(prev);
                    self.cursor_pos = prev;
                }
            }
            Delete => {
                if self.cursor_pos < self.input.len() {
                    self.input.remove(self.cursor_pos);
                }
            }
            Left => {
                if self.cursor_pos > 0 {
                    self.cursor_pos -= 1;
                }
            }
            Right => {
                if self.cursor_pos < self.input.len() {
                    self.cursor_pos += 1;
                }
            }
            Home => self.cursor_pos = 0,
            End => self.cursor_pos = self.input.len(),
            Up => self.history_up(),
            Down => self.history_down(),
            Esc => {
                self.input.clear();
                self.cursor_pos = 0;
                self.history_idx = None;
            }
            _ => {}
        }
    }

    fn history_up(&mut self) {
        if self.history.is_empty() {
            return;
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
                self.input.clear();
                self.cursor_pos = 0;
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
        self.input.clear();
        self.cursor_pos = 0;

        self.push_message(Message::user(&input));
        self.dispatch_command(input);
    }

    fn dispatch_command(&mut self, input: String) {
        if input.starts_with('/') {
            self.handle_slash_command(&input);
        } else {
            self.send_llm_query(input);
        }
    }

    // ── Background tasks ───────────────────────────────────────────────────

    pub(crate) fn start_background_index(&self) {
        let root = self.project_root.clone();
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            match nala_indexer::index_project(&root) {
                Ok(result) => {
                    let _ = tx
                        .send(BackgroundEvent::IndexComplete {
                            indexed_files: result.indexed_files,
                            total_files: result.scan_result.total_files,
                            symbols: result.total_symbols,
                            symbol_payload: result.symbols,
                        })
                        .await;
                }
                Err(e) => {
                    let _ = tx.send(BackgroundEvent::IndexError(e.to_string())).await;
                }
            }
        });
    }

    fn handle_background_event(&mut self, event: BackgroundEvent) {
        match event {
            BackgroundEvent::IndexComplete {
                indexed_files,
                total_files,
                symbols,
                symbol_payload,
            } => {
                self.index_progress = None;
                self.stats.total_files = total_files;
                self.stats.total_functions = symbols;
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
            BackgroundEvent::IndexError(e) => {
                self.index_progress = None;
                self.push_message(Message::error(format!("Index error: {}", e)));
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
            }
            BackgroundEvent::AssistantError(e) => {
                self.mode = AppMode::Ready;
                if let Some(partial) = self.streaming_response.take() {
                    if !partial.is_empty() {
                        self.push_message(Message::assistant(partial));
                    }
                }
                self.push_message(Message::error(format!("AI error: {}", e)));
            }
            BackgroundEvent::BridgeReady { has_llm } => {
                self.llm_available = has_llm;
                if has_llm {
                    self.status_text = "AI ready".to_string();
                } else {
                    self.status_text = "AI offline — add API key to .env".to_string();
                }
                if self.stats.total_files > 0 {
                    if let Some(bridge) = &self.python_bridge {
                        let bridge = bridge.clone();
                        let total_files = self.stats.total_files;
                        let total_symbols = self.stats.total_functions;
                        tokio::spawn(async move {
                            let _ = bridge
                                .index_context(total_files, total_symbols, Vec::new())
                                .await;
                        });
                    }
                }
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
                action_id: _,
                success,
                message,
                output,
            } => {
                if success {
                    let mut text = format!("Applied: {}", message);
                    if !output.is_empty() {
                        text.push('\n');
                        text.push_str(&output);
                    }
                    self.push_message(Message::system(text));
                } else {
                    self.push_message(Message::error(format!("Action failed: {}", message)));
                }
                self.show_next_pending_action();
            }
            BackgroundEvent::LspStarted { server_name } => {
                self.lsp_initialized = true;
                self.push_message(Message::system(format!(
                    "LSP: {} started (diagnostics active)",
                    server_name
                )));
            }
            BackgroundEvent::LspStartFailed(reason) => {
                self.push_message(Message::system(format!(
                    "LSP: not available — {}",
                    reason
                )));
            }
        }
    }

    pub(crate) fn start_lsp_background(&mut self) {
        let root = self.project_root.clone();
        let tx = self.bg_tx.clone();
        let diag_store = self.diagnostics_store.clone();
        tokio::spawn(async move {
            let mut manager =
                nala_lsp::LspManager::with_diagnostics_store(&root, diag_store);
            let server_name = manager.server().to_string();
            if server_name == "None" {
                let _ = tx
                    .send(BackgroundEvent::LspStartFailed(
                        "no supported language server found".into(),
                    ))
                    .await;
                return;
            }
            if let Err(e) = manager.initialize().await {
                let _ = tx
                    .send(BackgroundEvent::LspStartFailed(e.to_string()))
                    .await;
                return;
            }
            let _ = tx
                .send(BackgroundEvent::LspStarted { server_name })
                .await;

            // Keep the manager alive so the LSP server continues running and
            // pushing diagnostics. Park until the channel closes (app quits).
            let _ = tx.closed().await;
            let _ = manager.shutdown().await;
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
            }
        }
    }
}
