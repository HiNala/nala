//! Main layout compositor.
//!
//! Assembles all panels and widgets into the full-screen layout.
//! This is purely a rendering function — no state mutation happens here.
//!
//! Layout structure:
//!   ┌─────────────────────────────────────────────┐
//!   │ TOP BAR  (app name · project · branch · mode)│
//!   ├──────────┬──────────────────────┬────────────┤
//!   │ FILE     │                      │ SESSION    │
//!   │ PANEL    │  MAIN CONTENT AREA   │ PANEL      │
//!   │ (opt)    │  (message log)       │ (opt)      │
//!   ├──────────┴──────────────────────┴────────────┤
//!   │ COMMAND INPUT BAR                            │
//!   ├─────────────────────────────────────────────┤
//!   │ STATUS BAR                                  │
//!   └─────────────────────────────────────────────┘

use crate::app::{App, AppMode};
use crate::ui::{command_bar, diff, file_panel, session_panel, status_bar};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    // Outer vertical split: top_bar | body | command_input | status_bar
    let outer = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // top bar
            Constraint::Fill(1),   // body
            Constraint::Length(3), // command input
            Constraint::Length(1), // status bar
        ])
        .split(area);

    render_top_bar(frame, app, outer[0]);
    if app.mode == AppMode::Confirming && !app.pending_actions.is_empty() {
        diff::render_confirm(frame, app, outer[1]);
    } else {
        render_body(frame, app, outer[1]);
    }
    command_bar::render(frame, app, outer[2]);
    status_bar::render(frame, app, outer[3]);
}

// ── Top bar ────────────────────────────────────────────────────────────────

fn render_top_bar(frame: &mut Frame, app: &App, area: Rect) {
    let project_name = app
        .project_root
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown");

    let line = Line::from(vec![
        Span::styled(" HiNala ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
        Span::styled("│ ", Style::default().fg(Color::DarkGray)),
        Span::styled(project_name, Style::default().fg(Color::White)),
        Span::styled("  ", Style::default()),
        Span::styled(
            format!("[{}]", app.mode),
            Style::default().fg(Color::DarkGray),
        ),
    ]);

    frame.render_widget(
        Paragraph::new(line).style(Style::default().bg(Color::Rgb(20, 20, 30))),
        area,
    );
}

// ── Body ───────────────────────────────────────────────────────────────────

fn render_body(frame: &mut Frame, app: &App, area: Rect) {
    let left_open = app.panels.file_panel_open;
    let right_open = app.panels.session_panel_open;

    let constraints = match (left_open, right_open) {
        (true, true) => vec![
            Constraint::Length(28),
            Constraint::Fill(1),
            Constraint::Length(26),
        ],
        (true, false) => vec![Constraint::Length(28), Constraint::Fill(1)],
        (false, true) => vec![Constraint::Fill(1), Constraint::Length(26)],
        (false, false) => vec![Constraint::Fill(1)],
    };

    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints(constraints)
        .split(area);

    let mut col_idx = 0;

    if left_open {
        file_panel::render(frame, app, cols[col_idx]);
        col_idx += 1;
    }

    render_main_content(frame, app, cols[col_idx]);
    col_idx += 1;

    if right_open {
        session_panel::render(frame, app, cols[col_idx]);
    }
}

// ── Main content (message log) ─────────────────────────────────────────────

fn render_main_content(frame: &mut Frame, app: &App, area: Rect) {
    use crate::app::MessageKind;
    use ratatui::widgets::Wrap;

    let block = Block::default()
        .borders(Borders::LEFT | Borders::RIGHT)
        .border_style(Style::default().fg(Color::Rgb(40, 40, 60)))
        .style(Style::default().bg(Color::Rgb(10, 10, 18)));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    // Build the display lines from the message log
    let _inner_width = inner.width as usize;
    let mut lines: Vec<Line> = Vec::new();

    for msg in &app.messages {
        let (prefix, style) = match msg.kind {
            MessageKind::User => (
                "> ",
                Style::default().fg(Color::White).add_modifier(Modifier::BOLD),
            ),
            MessageKind::Assistant => (
                "  ",
                Style::default().fg(Color::Cyan),
            ),
            MessageKind::System => ("  ", Style::default().fg(Color::DarkGray)),
            MessageKind::Error => (
                "! ",
                Style::default().fg(Color::Red),
            ),
        };

        for (i, text_line) in msg.text.lines().enumerate() {
            let p = if i == 0 { prefix } else { "  " };
            lines.push(Line::from(Span::styled(
                format!("{}{}", p, text_line),
                style,
            )));
        }
        lines.push(Line::from("")); // spacing between messages
    }

    // Show streaming response if active
    if let Some(ref streaming) = app.streaming_response {
        for text_line in streaming.lines() {
            lines.push(Line::from(Span::styled(
                format!("  {}", text_line),
                Style::default().fg(Color::Cyan),
            )));
        }
        // Blinking cursor indicator
        lines.push(Line::from(Span::styled(
            "  ▋",
            Style::default().fg(Color::Cyan).add_modifier(Modifier::SLOW_BLINK),
        )));
    }

    // Scroll to bottom — only show the last N lines that fit
    let visible_height = inner.height as usize;
    let start = lines.len().saturating_sub(visible_height);
    let visible: Vec<Line> = lines.into_iter().skip(start).collect();

    frame.render_widget(
        Paragraph::new(visible)
            .wrap(Wrap { trim: false })
            .style(Style::default().bg(Color::Rgb(10, 10, 18))),
        inner,
    );
}
