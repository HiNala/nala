//! Application state machine and main event loop.
//!
//! `App` owns all UI state. The event loop polls crossterm for input events
//! and renders the UI at a capped frame rate (~30fps). Heavy work (indexing,
//! analysis) runs on Tokio background tasks and communicates back via channels.

use anyhow::Result;
use crossterm::event::{Event, EventStream, KeyCode, KeyModifiers};
use ratatui::{DefaultTerminal, Frame};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use tokio::sync::mpsc;
use tokio_stream::StreamExt;

use crate::python_bridge::PythonBridge;
use crate::ui;

// ── App mode ───────────────────────────────────────────────────────────────

/// The current operating mode of the application.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AppMode {
    /// Showing the boot splash screen.
    Booting,
    /// Ready and waiting for user input.
    Ready,
    /// User is typing a command.
    Command,
    /// Background analysis is running.
    Analyzing,
    /// Viewing a session report.
    Viewing,
    /// Awaiting user confirmation for a proposed action.
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

/// A proposed action awaiting user confirmation.
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
    /// Left file-tree panel (toggle: Ctrl+B).
    pub file_panel_open: bool,
    /// Right session-history panel (toggle: Ctrl+E).
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

/// Events sent from background tasks to the UI event loop.
#[derive(Debug)]
pub enum BackgroundEvent {
    IndexComplete { files: usize, symbols: usize },
    IndexError(String),
    AssistantChunk(String),
    AssistantDone,
    AssistantError(String),
    /// Python bridge is ready; carries whether an LLM key is configured.
    BridgeReady { has_llm: bool },
    /// Python proposed an inline action requiring user confirmation.
    ProposedAction {
        action_id: String,
        action_type: String,
        description: String,
        preview: String,
    },
    /// Python reports that an action was applied (or failed).
    ActionApplied {
        action_id: String,
        success: bool,
        message: String,
        output: String,
    },
}

// ── App ────────────────────────────────────────────────────────────────────

/// Central application state.
pub struct App {
    pub project_root: PathBuf,
    pub mode: AppMode,
    pub panels: PanelState,
    /// The text currently being typed in the command bar.
    pub input: String,
    /// Cursor position within `input` (byte offset).
    pub cursor_pos: usize,
    /// Command history (oldest first).
    pub history: Vec<String>,
    /// Current history navigation index (None = not navigating).
    pub history_idx: Option<usize>,
    /// Message log shown in the main content area.
    pub messages: Vec<Message>,
    /// Status line text.
    pub status_text: String,
    /// Indexing progress (0.0–1.0).
    pub index_progress: Option<f64>,
    /// Project stats shown in status bar.
    pub stats: ProjectStats,
    /// Splash screen start time.
    pub splash_start: Instant,
    /// Whether the app should exit on the next loop iteration.
    pub should_quit: bool,
    /// Channel receiver for background task events.
    pub bg_rx: mpsc::Receiver<BackgroundEvent>,
    /// Clone this to send events from background tasks.
    pub bg_tx: mpsc::Sender<BackgroundEvent>,
    /// Current AI response being streamed (appended chunk-by-chunk).
    pub streaming_response: Option<String>,
    /// Handle to the Python IPC bridge (None until the subprocess is ready).
    pub python_bridge: Option<PythonBridge>,
    /// Whether the LLM is available (set once bridge signals ready).
    pub llm_available: bool,
    /// Queue of proposed actions awaiting user confirmation.
    pub pending_actions: Vec<PendingAction>,
    /// Apply-all flag: skip remaining per-action prompts.
    pub apply_all: bool,
}

#[derive(Debug, Clone, Default)]
pub struct ProjectStats {
    pub total_files: usize,
    pub total_functions: usize,
    pub high_complexity_count: usize,
}

/// Maximum number of messages retained in the log to prevent unbounded growth.
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
        })
    }

    /// Append a message to the log, evicting old entries if over the cap.
    pub fn push_message(&mut self, msg: Message) {
        self.messages.push(msg);
        if self.messages.len() > MAX_MESSAGES {
            let drain = self.messages.len() - MAX_MESSAGES;
            self.messages.drain(0..drain);
        }
    }

    // ── Main loop ──────────────────────────────────────────────────────────

    /// Run the application until the user quits.
    pub async fn run(&mut self) -> Result<()> {
        let mut terminal = ratatui::init();

        // Spawn the Python bridge in the background. Failure here is non-fatal:
        // the UI will show a message when the user tries to query.
        self.start_python_bridge().await;

        let result = self.event_loop(&mut terminal).await;
        ratatui::restore();
        result
    }

    async fn event_loop(&mut self, terminal: &mut DefaultTerminal) -> Result<()> {
        let tick = Duration::from_millis(33); // ~30fps
        let mut reader = EventStream::new();
        let mut last_render = Instant::now();

        // Kick off background indexing
        self.start_background_index();

        loop {
            // Render if enough time has passed
            if last_render.elapsed() >= tick {
                terminal.draw(|f| self.render(f))?;
                last_render = Instant::now();
            }

            // Transition out of splash after 1.5s
            if self.mode == AppMode::Booting
                && self.splash_start.elapsed() > Duration::from_millis(1500)
            {
                self.mode = AppMode::Ready;
            }

            if self.should_quit {
                break;
            }

            // Poll for events with a short timeout so we can render regularly
            tokio::select! {
                // Terminal input events
                Some(Ok(event)) = reader.next() => {
                    self.handle_event(event);
                }

                // Background task messages
                Some(bg) = self.bg_rx.recv() => {
                    self.handle_background_event(bg);
                }

                // Yield to allow renders
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
            Event::Resize(_, _) => {} // Ratatui handles resize automatically
            Event::Mouse(_) => {}     // TODO: mouse support in Mission 04 polish
            _ => {}
        }
    }

    fn handle_key(&mut self, key: crossterm::event::KeyEvent) {
        use KeyCode::*;

        // Global shortcuts (work in any mode)
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
            return; // Ignore input during splash
        }

        // Confirming mode — handle action confirmation keys first
        if self.mode == AppMode::Confirming {
            self.handle_confirm_key(key.code);
            return;
        }

        match key.code {
            // Submit
            Enter => self.submit_input(),

            // Text editing
            Char(c) => {
                self.history_idx = None; // Break out of history nav
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

            // Cursor movement
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

            // History navigation
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

    fn run_perspectives(&mut self, perspective: String) {
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
                self.push_message(Message::system(format!(
                    "Running {} analysis...",
                    if perspective == "all" { "full".to_string() } else { perspective.clone() }
                )));
                tokio::spawn(async move {
                    if let Err(e) = bridge.run_perspectives(root, &perspective).await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
        }
    }

    fn send_llm_query(&mut self, text: String) {
        match &self.python_bridge {
            None => {
                self.push_message(Message::system(
                    "AI bridge is starting up — please wait a moment and try again.",
                ));
            }
            Some(_) if !self.llm_available => {
                self.push_message(Message::system(
                    "No LLM configured. Add ANTHROPIC_API_KEY (or OPENAI_API_KEY / GOOGLE_API_KEY) to .env and restart.",
                ));
            }
            Some(bridge) => {
                let bridge = bridge.clone();
                let root = self.project_root.clone();
                let tx = self.bg_tx.clone();
                self.mode = AppMode::Analyzing;
                tokio::spawn(async move {
                    if let Err(e) = bridge.query(text, root).await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
        }
    }

    fn handle_confirm_key(&mut self, code: KeyCode) {
        match code {
            // y / Enter — apply current action
            KeyCode::Char('y') | KeyCode::Enter => {
                self.apply_next_action();
            }
            // n — skip current action
            KeyCode::Char('n') => {
                self.skip_next_action();
            }
            // a — apply all remaining actions without further prompts
            KeyCode::Char('a') => {
                self.apply_all = true;
                self.apply_next_action();
            }
            // q / Esc — skip all remaining actions
            KeyCode::Char('q') | KeyCode::Esc => {
                self.skip_all_actions();
            }
            _ => {}
        }
    }

    fn apply_next_action(&mut self) {
        if let Some(action) = self.pending_actions.first().cloned() {
            let bridge = match &self.python_bridge {
                Some(b) => b.clone(),
                None => {
                    self.push_message(Message::error("Bridge not available."));
                    self.mode = AppMode::Ready;
                    return;
                }
            };
            let tx = self.bg_tx.clone();
            let id = action.action_id.clone();
            self.pending_actions.remove(0);
            tokio::spawn(async move {
                if let Err(e) = bridge.apply_action(id).await {
                    let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                }
            });
            // Show next pending action or return to Ready
            self.show_next_pending_action();
        }
    }

    fn skip_next_action(&mut self) {
        if let Some(action) = self.pending_actions.first().cloned() {
            let bridge = match &self.python_bridge {
                Some(b) => b.clone(),
                None => {
                    self.pending_actions.clear();
                    self.mode = AppMode::Ready;
                    return;
                }
            };
            let id = action.action_id.clone();
            self.pending_actions.remove(0);
            let tx = self.bg_tx.clone();
            tokio::spawn(async move {
                let _ = bridge.skip_action(id).await;
                // no event needed — fire and forget
                drop(tx);
            });
            self.push_message(Message::system("Skipped."));
            self.show_next_pending_action();
        }
    }

    fn skip_all_actions(&mut self) {
        let bridge = self.python_bridge.clone();
        let ids: Vec<String> = self.pending_actions.drain(..).map(|a| a.action_id).collect();
        if let Some(bridge) = bridge {
            tokio::spawn(async move {
                for id in ids {
                    let _ = bridge.skip_action(id).await;
                }
            });
        }
        self.push_message(Message::system("Skipped all proposed actions."));
        self.apply_all = false;
        self.mode = AppMode::Ready;
    }

    fn show_next_pending_action(&mut self) {
        if let Some(next) = self.pending_actions.first() {
            if self.apply_all {
                self.apply_next_action();
            } else {
                self.push_message(Message::assistant(format!(
                    "**[{} — {}]**\n{}\n\n[y] Apply  [n] Skip  [a] Apply all  [q] Skip all",
                    next.action_type, next.description, next.preview,
                )));
                self.mode = AppMode::Confirming;
            }
        } else {
            self.apply_all = false;
            self.mode = AppMode::Ready;
        }
    }

    fn handle_slash_command(&mut self, cmd: &str) {
        let parts: Vec<&str> = cmd.splitn(2, ' ').collect();
        match parts[0] {
            "/help" => {
                self.push_message(Message::assistant(
                    "Available commands:\n  /scan               — scan project files\n  /index              — full index (parse + symbols)\n  /analyze            — run all analysis perspectives\n  /analyze <name>     — run one perspective (security, complexity, …)\n  /act <instruction>  — ask AI to make changes (with diff preview + confirm)\n  /session            — list past sessions\n  /session new        — start a fresh session\n  /session load <id>  — resume a past session\n  /session summary    — show current session summary\n  /generate           — generate a mission doc from findings\n  /generate <focus>   — generate focused on a topic\n  /context            — show context window usage breakdown\n  /compact            — compact context window to free tokens\n  /compact <focus>    — compact while preserving focus topic\n  /clear              — clear message log\n  /help               — show this help\n  /quit               — exit\n\nOr just type a question to ask the AI.",
                ));
            }
            "/quit" | "/exit" => {
                self.should_quit = true;
            }
            "/scan" => {
                self.push_message(Message::system("Scanning project..."));
                self.start_background_index();
            }
            "/index" => {
                self.push_message(Message::system("Indexing project..."));
                self.start_background_index();
            }
            "/analyze" | "/analyse" => {
                let perspective = parts.get(1).copied().unwrap_or("all").to_string();
                self.run_perspectives(perspective);
            }
            "/session" => {
                let args = parts.get(1).copied().unwrap_or("").trim();
                self.handle_session_command(args);
            }
            "/generate" => {
                let focus = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.generate_mission(focus);
            }
            "/act" => {
                let query = parts.get(1).copied().unwrap_or("").trim().to_string();
                if query.is_empty() {
                    self.push_message(Message::error("Usage: /act <instruction>"));
                } else {
                    self.send_action_query(query);
                }
            }
            "/context" => {
                self.show_context_usage();
            }
            "/compact" => {
                let focus = parts.get(1).copied().unwrap_or("").trim().to_string();
                self.compact_context(focus);
            }
            "/clear" => {
                self.messages.clear();
            }
            _ => {
                self.push_message(Message::error(format!("Unknown command: {}. Type /help.", parts[0])));
            }
        }
    }

    fn show_context_usage(&mut self) {
        match &self.python_bridge {
            None => self.push_message(Message::system("AI bridge not ready.")),
            Some(bridge) => {
                let bridge = bridge.clone();
                let tx = self.bg_tx.clone();
                tokio::spawn(async move {
                    if let Err(e) = bridge.context_usage().await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
        }
    }

    fn compact_context(&mut self, focus: String) {
        match &self.python_bridge {
            None => self.push_message(Message::system("AI bridge not ready.")),
            Some(bridge) => {
                let bridge = bridge.clone();
                let tx = self.bg_tx.clone();
                self.push_message(Message::system("Compacting context window..."));
                tokio::spawn(async move {
                    if let Err(e) = bridge.compact_context(focus).await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
        }
    }

    fn handle_session_command(&mut self, args: &str) {
        let sub: Vec<&str> = args.splitn(2, ' ').collect();
        match sub[0] {
            "" => {
                // List sessions
                match &self.python_bridge {
                    None => self.push_message(Message::system("AI bridge not ready.")),
                    Some(bridge) => {
                        let bridge = bridge.clone();
                        let root = self.project_root.clone();
                        let tx = self.bg_tx.clone();
                        self.push_message(Message::system("Fetching sessions..."));
                        tokio::spawn(async move {
                            if let Err(e) = bridge.list_sessions(root).await {
                                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                            }
                        });
                    }
                }
            }
            "new" => {
                match &self.python_bridge {
                    None => self.push_message(Message::system("AI bridge not ready.")),
                    Some(bridge) => {
                        let bridge = bridge.clone();
                        let tx = self.bg_tx.clone();
                        tokio::spawn(async move {
                            if let Err(e) = bridge.new_session().await {
                                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                            }
                        });
                    }
                }
            }
            "load" => {
                let session_id = sub.get(1).copied().unwrap_or("").trim().to_string();
                if session_id.is_empty() {
                    self.push_message(Message::error("Usage: /session load <session_id>"));
                    return;
                }
                match &self.python_bridge {
                    None => self.push_message(Message::system("AI bridge not ready.")),
                    Some(bridge) => {
                        let bridge = bridge.clone();
                        let tx = self.bg_tx.clone();
                        self.push_message(Message::system(format!("Loading session {}...", session_id)));
                        tokio::spawn(async move {
                            if let Err(e) = bridge.load_session(session_id).await {
                                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                            }
                        });
                    }
                }
            }
            "summary" => {
                match &self.python_bridge {
                    None => self.push_message(Message::system("AI bridge not ready.")),
                    Some(bridge) => {
                        let bridge = bridge.clone();
                        let tx = self.bg_tx.clone();
                        tokio::spawn(async move {
                            if let Err(e) = bridge.session_summary().await {
                                let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                            }
                        });
                    }
                }
            }
            _ => {
                self.push_message(Message::error(
                    format!("Unknown session subcommand: '{}'. Use: new, load <id>, summary.", sub[0])
                ));
            }
        }
    }

    fn send_action_query(&mut self, text: String) {
        match &self.python_bridge {
            None => {
                self.push_message(Message::system("AI bridge not ready."));
            }
            Some(_) if !self.llm_available => {
                self.push_message(Message::system(
                    "No LLM configured — cannot run action query. Add an API key to .env."
                ));
            }
            Some(bridge) => {
                let bridge = bridge.clone();
                let root = self.project_root.clone();
                let tx = self.bg_tx.clone();
                self.mode = AppMode::Analyzing;
                self.push_message(Message::system("Thinking... (action mode)"));
                tokio::spawn(async move {
                    if let Err(e) = bridge.query_with_actions(text, root).await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
        }
    }

    fn generate_mission(&mut self, focus: String) {
        match &self.python_bridge {
            None => {
                self.push_message(Message::system("AI bridge not ready."));
            }
            Some(_) if !self.llm_available => {
                self.push_message(Message::system(
                    "No LLM configured — cannot generate mission. Add an API key to .env."
                ));
            }
            Some(bridge) => {
                let bridge = bridge.clone();
                let tx = self.bg_tx.clone();
                self.mode = AppMode::Analyzing;
                let label = if focus.is_empty() {
                    "Generating mission document...".to_string()
                } else {
                    format!("Generating mission focused on: {}...", focus)
                };
                self.push_message(Message::system(label));
                tokio::spawn(async move {
                    if let Err(e) = bridge.generate_mission(focus).await {
                        let _ = tx.send(BackgroundEvent::AssistantError(e.to_string())).await;
                    }
                });
            }
        }
    }

    // ── Background tasks ───────────────────────────────────────────────────

    fn start_background_index(&self) {
        let root = self.project_root.clone();
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            match nala_indexer::index_project(&root) {
                Ok(result) => {
                    let _ = tx.send(BackgroundEvent::IndexComplete {
                        files: result.indexed_files,
                        symbols: result.total_symbols,
                    }).await;
                }
                Err(e) => {
                    let _ = tx.send(BackgroundEvent::IndexError(e.to_string())).await;
                }
            }
        });
    }

    fn handle_background_event(&mut self, event: BackgroundEvent) {
        match event {
            BackgroundEvent::IndexComplete { files, symbols } => {
                self.index_progress = None;
                self.stats.total_files = files;
                self.status_text = format!("{} files indexed • {} symbols", files, symbols);
                if files > 0 {
                    self.push_message(Message::system(format!(
                        "Index complete: {} files, {} symbols.", files, symbols
                    )));
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
                // Flush any partial streaming response before showing error
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
            }
            BackgroundEvent::ProposedAction { action_id, action_type, description, preview } => {
                self.pending_actions.push(PendingAction {
                    action_id,
                    action_type,
                    description,
                    preview,
                });
                // If not already in Confirming mode, show the first action
                if self.mode != AppMode::Confirming {
                    self.show_next_pending_action();
                }
            }
            BackgroundEvent::ActionApplied { action_id: _, success, message, output } => {
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
                // Show next pending action (if any)
                self.show_next_pending_action();
            }
        }
    }

    // ── Python bridge ──────────────────────────────────────────────────────

    async fn start_python_bridge(&mut self) {
        let root = self.project_root.clone();
        let bg_tx = self.bg_tx.clone();

        match crate::python_bridge::spawn(&root, bg_tx.clone()).await {
            Ok(bridge) => {
                self.python_bridge = Some(bridge);
                // BridgeReady will arrive via BackgroundEvent once the subprocess
                // sends its "ready" line — handled in handle_background_event.
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
