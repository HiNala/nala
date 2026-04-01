//! Diff/preview renderer for Confirming mode.
//!
//! Renders a unified diff (or action preview) with:
//! - Red lines for removals  (`-` prefix)
//! - Green lines for additions (`+` prefix)
//! - Gray lines for context / metadata (`@` / `---` / `+++`)
//! - White lines for everything else

use crate::app::{App, PendingAction};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

const MAX_PREVIEW_LINES: usize = 30;

/// Render the Confirming-mode overlay.
///
/// Shows the current pending action's diff/preview and the confirmation
/// key-binding bar at the bottom.
pub fn render_confirm(frame: &mut Frame, app: &App, area: Rect) {
    let action = match app.pending_actions.first() {
        Some(a) => a,
        None => return,
    };

    // Split area: header | diff | key-hint
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // header
            Constraint::Fill(1),   // diff preview
            Constraint::Length(1), // key hint
        ])
        .split(area);

    render_header(frame, action, chunks[0]);
    render_preview(frame, action, chunks[1]);
    render_hint(frame, app, chunks[2]);
}

fn render_header(frame: &mut Frame, action: &PendingAction, area: Rect) {
    let title = format!(
        " Action: [{}] {} ",
        action.action_type.to_uppercase(),
        action.description,
    );
    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Yellow))
        .style(Style::default().bg(Color::Rgb(10, 10, 18)));
    frame.render_widget(block, area);
}

fn render_preview(frame: &mut Frame, action: &PendingAction, area: Rect) {
    let block = Block::default()
        .borders(Borders::LEFT | Borders::RIGHT | Borders::BOTTOM)
        .border_style(Style::default().fg(Color::DarkGray))
        .style(Style::default().bg(Color::Rgb(10, 10, 18)));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let lines: Vec<Line> = action
        .preview
        .lines()
        .take(MAX_PREVIEW_LINES)
        .map(|l| colorize_diff_line(l))
        .collect();

    let total = action.preview.lines().count();
    let mut all_lines = lines;
    if total > MAX_PREVIEW_LINES {
        all_lines.push(Line::from(Span::styled(
            format!("  ... {} more lines", total - MAX_PREVIEW_LINES),
            Style::default().fg(Color::DarkGray),
        )));
    }

    frame.render_widget(
        Paragraph::new(all_lines).wrap(Wrap { trim: false }),
        inner,
    );
}

fn render_hint(frame: &mut Frame, app: &App, area: Rect) {
    let remaining = app.pending_actions.len();
    let hint = format!(
        " [y] Apply  [n] Skip  [a] Apply all  [q] Skip all    ({} action{} pending)",
        remaining,
        if remaining == 1 { "" } else { "s" },
    );
    frame.render_widget(
        Paragraph::new(hint).style(Style::default().fg(Color::Yellow).bg(Color::Rgb(20, 15, 0))),
        area,
    );
}

fn colorize_diff_line(line: &str) -> Line<'static> {
    let line = line.to_owned();
    if line.starts_with('+') && !line.starts_with("+++") {
        Line::from(Span::styled(
            line,
            Style::default().fg(Color::Green),
        ))
    } else if line.starts_with('-') && !line.starts_with("---") {
        Line::from(Span::styled(
            line,
            Style::default().fg(Color::Red),
        ))
    } else if line.starts_with("@@") || line.starts_with("---") || line.starts_with("+++") {
        Line::from(Span::styled(
            line,
            Style::default().fg(Color::DarkGray).add_modifier(Modifier::BOLD),
        ))
    } else if line.starts_with('$') {
        // Shell command preview
        Line::from(Span::styled(
            line,
            Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
        ))
    } else {
        Line::from(Span::styled(line, Style::default().fg(Color::White)))
    }
}
