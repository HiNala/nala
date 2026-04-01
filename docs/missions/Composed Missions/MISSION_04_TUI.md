# Mission 04: TUI Shell and Boot Experience

## Objective

Build the terminal user interface that gives Nala its identity. Type `nala` → clean, polished boot sequence → responsive workspace. This is the face of the product.

## Status

**Core implementation in place.** See:
- `rust-core/nala-tui/src/app.rs` — App state machine, event loop, keyboard handling
- `rust-core/nala-tui/src/ui/splash.rs` — Boot splash with ASCII logo
- `rust-core/nala-tui/src/ui/layout.rs` — Main layout compositor
- `rust-core/nala-tui/src/ui/command_bar.rs` — Command input with cursor
- `rust-core/nala-tui/src/ui/status_bar.rs` — Status bar with mode + shortcuts
- `rust-core/nala-tui/src/ui/file_panel.rs` — File tree (Ctrl+B)
- `rust-core/nala-tui/src/ui/session_panel.rs` — Session history (Ctrl+E)

## Polish Items for This Mission

### Mouse support
Add `crossterm::event::EnableMouseCapture` in the terminal init. Handle `Event::Mouse` events in `app.rs` for clicking list items.

### Tab completion
In `command_bar.rs`, implement tab completion for slash commands. Maintain a `completions: Vec<String>` list. On Tab key, cycle through matching commands.

### Resize handling
Test the layout at narrow widths (< 80 columns). Ensure panels collapse gracefully when the terminal is too small.

### Smooth cursor blink
The cursor in `command_bar.rs` should blink. Use the `Modifier::SLOW_BLINK` attribute already set and verify it renders correctly in different terminals.

### Wire Python agent to TUI
The `dispatch_command()` function in `app.rs` currently shows a placeholder for non-slash queries. This mission connects it to the Python orchestrator via the PyO3 bridge:

```rust
// In app.rs dispatch_command():
// Start a tokio::spawn that calls Python agent and sends chunks via bg_tx
```

## Acceptance Criteria

- [ ] `nala` boots to splash in under 500ms
- [ ] Splash transitions to main workspace within 2 seconds
- [ ] Command input accepts text, supports history (↑/↓), handles slash commands
- [ ] File panel toggles with Ctrl+B
- [ ] Session panel toggles with Ctrl+E
- [ ] Status bar shows real-time project stats
- [ ] Background indexing runs on boot and shows progress
- [ ] TUI renders correctly at terminal widths from 80 to 220+ columns
- [ ] No source file exceeds 400 lines
