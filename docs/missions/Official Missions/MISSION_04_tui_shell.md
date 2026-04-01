# Mission 04: TUI Shell and Boot Experience

## Objective

Build the terminal user interface that gives Nala its identity. When the user types `nala` and hits Enter, they should see a clean, polished boot sequence followed by a responsive, keyboard-and-mouse-driven workspace. This mission creates the main TUI shell with the command prompt, togglable side panels, status bar, and the SSH-style boot experience inspired by OpenCode and Claude Code.

## Why This Matters

The TUI is the face of Nala. It is what the user interacts with every time they use the tool. If it feels slow, ugly, or confusing, no amount of powerful analysis behind the scenes will save the product. The boot experience sets the emotional tone. OpenCode nails this with a clean, instant TUI built on Bubble Tea (Go). Claude Code nails it with its SSH-style terminal entry. Nala needs to feel at least as good, and ideally better, because Ratatui gives us sub-millisecond rendering with zero-cost abstractions.

The design philosophy here comes from Dieter Rams (every element justifies its existence), Jef Raskin (flow without interruption), and Larry Tesler (modeless, direct, reversible interactions). The TUI should feel calm, inevitable, and fast.

## Context

This work happens in the `nala-tui` crate. It depends on `nala-indexer` for displaying scan/index results and `nala-cli` for the entry point.

## Implementation Steps

### Step 1: Build the app state machine (app.rs)

Create an `App` struct that holds the entire application state:
- `mode: AppMode` (enum: Booting, Ready, Command, Analyzing, Viewing)
- `panels: PanelState` (which panels are visible: file_tree, session_panel)
- `command_input: String` (current command being typed)
- `command_history: Vec<String>` (previous commands for up/down navigation)
- `messages: Vec<Message>` (chat-style message log, similar to Claude Code)
- `status: StatusInfo` (current status text, indexing progress, etc.)
- `project_root: PathBuf`
- `should_quit: bool`

Create an event loop using tokio that:
1. Draws the UI on each frame (target 30fps to keep CPU low)
2. Polls for keyboard and mouse events via crossterm
3. Dispatches events to handler functions that update the App state
4. Redraws when state changes

### Step 2: Build the boot splash (splash.rs)

Create a splash screen that displays for 1-2 seconds on launch:
- A minimal ASCII art logo or the word "NALA" in a clean font
- Version number
- A subtle progress indicator if indexing is happening in the background

Keep it tasteful. No gaudy ASCII art. Think of the OpenCode boot screen or the Claude Code startup message. Clean, professional, brief.

After the splash, transition to the main workspace with a smooth crossfade (clear screen, render main layout).

### Step 3: Build the main layout (layout.rs)

The main layout has these regions, using Ratatui's constraint-based layout system:

- Top bar: App name, project name, current branch (from git), connection status
- Left panel (togglable, default hidden): File tree browser. Shows the project directory structure. Files are clickable (mouse) or navigable (keyboard arrows + enter).
- Center area: Main content area. This is a scrollable message log, similar to how Claude Code and OpenCode display conversation history. Commands the user types appear here, along with results from analysis, navigation, and agent actions.
- Right panel (togglable, default hidden): Context panel. Shows session summaries, quick stats (total files, total functions, top complexity), or the current file's symbol outline.
- Bottom: Command input bar. This is where the user types commands. Supports tab completion, command history (up/down arrows), and inline hints.
- Status bar: Below the command input. Shows current mode, indexing status, file count, and keyboard shortcuts.

### Step 4: Build the command input bar (command_bar.rs)

The command bar is the primary interaction point. It should feel like a terminal prompt but smarter.

Features:
- Text input with cursor movement (home, end, left, right, ctrl+left/right for word jump)
- Command history navigation with up/down arrows
- Slash commands: `/scan`, `/index`, `/analyze`, `/session`, `/help`, `/quit`
- Free text input for agent queries (anything not starting with `/` is treated as a natural language query for the AI agent)
- Tab completion for slash commands and file paths
- Visual distinction between user input and system responses in the message log

### Step 5: Build the file tree panel (file_panel.rs)

A collapsible tree view of the project directory. Toggle with `Ctrl+B` (matching VS Code convention for sidebar toggle).

Features:
- Directories are expandable/collapsible
- Files show their language icon (or just the extension) and a color indicator for their health (green = low complexity, yellow = medium, red = high)
- Click a file (mouse) or select and press Enter (keyboard) to show its symbol outline in the right panel
- Respects the same exclusion rules as the scanner (no node_modules, target, etc.)

### Step 6: Build the session panel (session_panel.rs)

Toggle with `Ctrl+E`. Shows a list of previous analysis sessions with timestamps and summary stats. Select a session to view its report in the main area.

### Step 7: Build the status bar (status_bar.rs)

A single line at the bottom showing:
- Current mode (READY, INDEXING, ANALYZING, etc.)
- Project stats (e.g., "1,247 files | 892 functions | 12 high-complexity")
- Keyboard shortcut hints (e.g., "Ctrl+B: Files | Ctrl+E: Sessions | /help")
- Indexing progress bar when indexing is active

### Step 8: Wire up keyboard and mouse events

Handle these key bindings:
- Escape: Cancel current operation or close panel
- Ctrl+C or Ctrl+Q: Quit
- Ctrl+B: Toggle file panel
- Ctrl+E: Toggle session panel
- Enter: Submit command
- Up/Down: Command history (when command bar is focused)
- Tab: Autocomplete
- Mouse click: Select items in panels, click on file tree entries

### Step 9: Connect to the indexer

On boot, after the splash screen, automatically run `scan_project()` in the background. Show progress in the status bar. When complete, update the file panel and status bar with results. If the project has been indexed before (cache exists), this should be nearly instant.

### Step 10: Write tests

- Test that the App state machine transitions correctly between modes
- Test command parsing (slash commands vs free text)
- Test command history navigation
- Render tests using Ratatui's TestBackend to verify layout does not panic

## Acceptance Criteria

- `nala` boots to the splash screen in under 500ms
- Splash transitions to the main workspace within 2 seconds
- Command input accepts text, supports history, and handles slash commands
- File panel toggles on/off with Ctrl+B
- Session panel toggles on/off with Ctrl+E
- Status bar shows real-time project stats
- Background indexing runs on boot and shows progress
- Mouse clicks work for panel navigation
- The TUI feels responsive at all times (no frame drops, no input lag)
- No source file exceeds 400 lines

## Key Dependencies

- ratatui (TUI framework)
- crossterm (terminal events and raw mode)
- tokio (async event loop)

## Estimated Complexity

High. Building a polished TUI with multiple panels, keyboard handling, mouse support, and async background operations is a significant engineering effort. Getting the layout constraints right across different terminal sizes requires careful testing.
