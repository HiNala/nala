//! Command input area.
//!
//! Two lines: a thin horizontal separator, then the `> ` prompt.
//! Clean, professional feel inspired by Claude Code / Gemini CLI.

use crate::app::{self, App};
use crate::ui::theme;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Length(1)])
        .split(area);

    let sep_char = "─".repeat(area.width as usize);
    let separator = Line::from(Span::styled(
        sep_char,
        Style::default().fg(theme::GRAY),
    ));
    frame.render_widget(Paragraph::new(separator), rows[0]);

    let is_slash = app.input.starts_with('/');

    let input_style = if is_slash {
        Style::default().fg(theme::YELLOW)
    } else {
        Style::default().fg(theme::WHITE)
    };

    let content = if app.input.is_empty() {
        Line::from(vec![
            Span::styled(
                " > ",
                Style::default()
                    .fg(theme::GREEN)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                "Type a question or /help for commands",
                Style::default().fg(theme::GRAY),
            ),
        ])
    } else {
        let mut spans = vec![
            Span::styled(
                " > ",
                Style::default()
                    .fg(theme::GREEN)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(&app.input[..], input_style),
        ];

        if let Some(hint) = app::tab_hint(&app.input) {
            let ghost = &hint[app.input.len()..];
            spans.push(Span::styled(ghost, Style::default().fg(theme::GRAY)));
        }

        Line::from(spans)
    };

    frame.render_widget(Paragraph::new(content), rows[1]);
}
