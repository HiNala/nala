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
}

impl std::fmt::Display for AppMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Booting => write!(f, "BOOTING"),
            Self::Ready => write!(f, "READY"),
            Self::Command => write!(f, "COMMAND"),
            Self::Analyzing => write!(f, "ANALYZING"),
            Self::Viewing => write!(f, "VIEWING"),
        }
    }
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
}

#[derive(Debug, Clone, Default)]
pub struct ProjectStats {
    pub total_files: usize,
    pub total_functions: usize,
    pub high_complexity_count: usize,
}

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
        })
    }

    // ── Main loop ──────────────────────────────────────────────────────────

    /// Run the application until the user quits.
    pub async fn run(&mut self) -> Result<()> {
        let mut terminal = ratatui::init();
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

        self.messages.push(Message::user(&input));
        self.dispatch_command(input);
    }

    fn dispatch_command(&mut self, input: String) {
        if input.starts_with('/') {
            self.handle_slash_command(&input);
        } else {
            // Natural language query — will be routed to the LLM in Mission 12
            self.messages.push(Message::system(
                "AI assistant not yet configured. Add your API key to .env and restart.",
            ));
        }
    }

    fn handle_slash_command(&mut self, cmd: &str) {
        let parts: Vec<&str> = cmd.splitn(2, ' ').collect();
        match parts[0] {
            "/help" => {
                self.messages.push(Message::assistant(
                    "Available commands:\n  /scan    — scan project files\n  /index   — full index (parse + symbols)\n  /analyze — run analysis perspectives\n  /session — list sessions\n  /help    — show this help\n  /quit    — exit\n\nOr just type a question to ask the AI.",
                ));
            }
            "/quit" | "/exit" => {
                self.should_quit = true;
            }
            "/scan" => {
                self.messages.push(Message::system("Scanning project..."));
                self.start_background_index();
            }
            "/index" => {
                self.messages.push(Message::system("Indexing project..."));
                self.start_background_index();
            }
            "/clear" => {
                self.messages.clear();
            }
            _ => {
                self.messages.push(Message::error(format!("Unknown command: {}. Type /help.", parts[0])));
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
                    self.messages.push(Message::system(format!(
                        "Index complete: {} files, {} symbols.", files, symbols
                    )));
                }
            }
            BackgroundEvent::IndexError(e) => {
                self.index_progress = None;
                self.messages.push(Message::error(format!("Index error: {}", e)));
            }
            BackgroundEvent::AssistantChunk(chunk) => {
                if let Some(ref mut resp) = self.streaming_response {
                    resp.push_str(&chunk);
                } else {
                    self.streaming_response = Some(chunk);
                }
            }
            BackgroundEvent::AssistantDone => {
                if let Some(text) = self.streaming_response.take() {
                    self.messages.push(Message::assistant(text));
                }
            }
        }
    }
}
