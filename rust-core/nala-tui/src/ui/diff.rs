//! Diff/preview renderer for Confirming mode.
//!
//! Renders a unified diff (or action preview) with color-coded lines.

use crate::app::{App, PendingAction};
use crate::ui::theme;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

const MAX_PREVIEW_LINES: usize = 30;

pub fn render_confirm(frame: &mut Frame, app: &App, area: Rect) {
    let action = match app.pending_actions.first() {
        Some(a) => a,
        None => return,
    };

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Fill(1),
            Constraint::Length(1),
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
        .title_style(Style::default().fg(theme::ACCENT_WARM).add_modifier(Modifier::BOLD))
        .borders(Borders::ALL)
        .border_style(Style::default().fg(theme::WARNING))
        .style(theme::base_style());
    frame.render_widget(block, area);
}

fn render_preview(frame: &mut Frame, action: &PendingAction, area: Rect) {
    let block = Block::default()
        .borders(Borders::LEFT | Borders::RIGHT | Borders::BOTTOM)
        .border_style(Style::default().fg(theme::BORDER_NORMAL))
        .style(theme::base_style());

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let lines: Vec<Line> = action
        .preview
        .lines()
        .take(MAX_PREVIEW_LINES)
        .map(colorize_diff_line)
        .collect();

    let total = action.preview.lines().count();
    let mut all_lines = lines;
    if total > MAX_PREVIEW_LINES {
        all_lines.push(Line::from(Span::styled(
            format!("  ... {} more lines", total - MAX_PREVIEW_LINES),
            Style::default().fg(theme::FG_DIM),
        )));
    }

    frame.render_widget(
        Paragraph::new(all_lines).wrap(Wrap { trim: false }),
        inner,
    );
}

fn render_hint(frame: &mut Frame, app: &App, area: Rect) {
    let remaining = app.pending_actions.len();
    let hint = Line::from(vec![
        Span::styled(" [y]", Style::default().fg(theme::ACCENT_GREEN).add_modifier(Modifier::BOLD)),
        Span::styled(" Apply  ", Style::default().fg(theme::FG_SECONDARY)),
        Span::styled("[n]", Style::default().fg(theme::ACCENT_ROSE).add_modifier(Modifier::BOLD)),
        Span::styled(" Skip  ", Style::default().fg(theme::FG_SECONDARY)),
        Span::styled("[a]", Style::default().fg(theme::ACCENT_PRIMARY).add_modifier(Modifier::BOLD)),
        Span::styled(" Apply all  ", Style::default().fg(theme::FG_SECONDARY)),
        Span::styled("[q]", Style::default().fg(theme::FG_DIM).add_modifier(Modifier::BOLD)),
        Span::styled(" Skip all  ", Style::default().fg(theme::FG_SECONDARY)),
        Span::styled(
            format!("  ({} pending)", remaining),
            Style::default().fg(theme::FG_MUTED),
        ),
    ]);
    frame.render_widget(
        Paragraph::new(hint).style(Style::default().bg(theme::BG_ELEVATED)),
        area,
    );
}

fn colorize_diff_line(line: &str) -> Line<'static> {
    let line = line.to_owned();
    if line.starts_with('+') && !line.starts_with("+++") {
        Line::from(Span::styled(line, Style::default().fg(theme::DIFF_ADD)))
    } else if line.starts_with('-') && !line.starts_with("---") {
        Line::from(Span::styled(line, Style::default().fg(theme::DIFF_REMOVE)))
    } else if line.starts_with("@@") || line.starts_with("---") || line.starts_with("+++") {
        Line::from(Span::styled(
            line,
            Style::default()
                .fg(theme::FG_MUTED)
                .add_modifier(Modifier::BOLD),
        ))
    } else if line.starts_with('$') {
        Line::from(Span::styled(
            line,
            Style::default()
                .fg(theme::ACCENT_PRIMARY)
                .add_modifier(Modifier::BOLD),
        ))
    } else {
        Line::from(Span::styled(
            line,
            Style::default().fg(theme::DIFF_CONTEXT),
        ))
    }
}
