//! Diff/preview renderer for Confirming mode.
//! Terminal-native colors for diff display.

use crate::app::{App, PendingAction};
use crate::ui::theme;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Paragraph, Wrap},
    Frame,
};

const MAX_PREVIEW_LINES: usize = 40;

pub fn render_confirm(frame: &mut Frame, app: &App, area: Rect) {
    let action = match app.pending_actions.first() {
        Some(a) => a,
        None => return,
    };

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(2), Constraint::Fill(1), Constraint::Length(1)])
        .split(area);

    render_header(frame, action, chunks[0]);
    render_preview(frame, action, chunks[1]);
    render_hint(frame, app, chunks[2]);
}

fn render_header(frame: &mut Frame, action: &PendingAction, area: Rect) {
    let lines = vec![
        Line::from(""),
        Line::from(vec![
            Span::styled("  Action: ", Style::default().fg(theme::YELLOW).add_modifier(Modifier::BOLD)),
            Span::styled(
                format!("[{}] {}", action.action_type.to_uppercase(), action.description),
                Style::default().fg(theme::WHITE),
            ),
        ]),
    ];
    frame.render_widget(Paragraph::new(lines), area);
}

fn render_preview(frame: &mut Frame, action: &PendingAction, area: Rect) {
    let mut lines: Vec<Line> = action
        .preview
        .lines()
        .take(MAX_PREVIEW_LINES)
        .map(colorize_diff_line)
        .collect();

    let total = action.preview.lines().count();
    if total > MAX_PREVIEW_LINES {
        lines.push(Line::from(Span::styled(
            format!("  ... {} more lines", total - MAX_PREVIEW_LINES),
            Style::default().fg(theme::DARK_GRAY),
        )));
    }

    frame.render_widget(Paragraph::new(lines).wrap(Wrap { trim: false }), area);
}

fn render_hint(frame: &mut Frame, app: &App, area: Rect) {
    let remaining = app.pending_actions.len();
    let hint = Line::from(vec![
        Span::styled(" [y]", Style::default().fg(theme::GREEN).add_modifier(Modifier::BOLD)),
        Span::styled(" apply  ", Style::default().fg(theme::GRAY)),
        Span::styled("[n]", Style::default().fg(theme::RED).add_modifier(Modifier::BOLD)),
        Span::styled(" skip  ", Style::default().fg(theme::GRAY)),
        Span::styled("[a]", Style::default().fg(theme::CYAN).add_modifier(Modifier::BOLD)),
        Span::styled(" all  ", Style::default().fg(theme::GRAY)),
        Span::styled("[q]", Style::default().fg(theme::DARK_GRAY).add_modifier(Modifier::BOLD)),
        Span::styled(" skip all  ", Style::default().fg(theme::GRAY)),
        Span::styled(
            format!("({} pending)", remaining),
            Style::default().fg(theme::DARK_GRAY),
        ),
    ]);
    frame.render_widget(Paragraph::new(hint), area);
}

fn colorize_diff_line(line: &str) -> Line<'static> {
    let line = line.to_owned();
    if line.starts_with('+') && !line.starts_with("+++") {
        Line::from(Span::styled(format!("  {}", line), Style::default().fg(theme::DIFF_ADD)))
    } else if line.starts_with('-') && !line.starts_with("---") {
        Line::from(Span::styled(format!("  {}", line), Style::default().fg(theme::DIFF_REMOVE)))
    } else if line.starts_with("@@") || line.starts_with("---") || line.starts_with("+++") {
        Line::from(Span::styled(
            format!("  {}", line),
            Style::default().fg(theme::DARK_GRAY).add_modifier(Modifier::BOLD),
        ))
    } else {
        Line::from(Span::styled(format!("  {}", line), Style::default().fg(theme::GRAY)))
    }
}
