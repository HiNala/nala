//! Command input line.
//!
//! Simple `> ` prompt like Claude Code / Gemini CLI.
//! No box, no border -- just a prompt and the user's text.

use crate::app::{self, App};
use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let is_slash = app.input.starts_with('/');

    let input_style = if is_slash {
        Style::default().fg(theme::YELLOW)
    } else {
        Style::default().fg(theme::WHITE)
    };

    let content = if app.input.is_empty() {
        Line::from(vec![
            Span::styled("> ", Style::default().fg(theme::CYAN).add_modifier(Modifier::BOLD)),
            Span::styled(
                "Type a question or /help for commands",
                Style::default().fg(theme::DARK_GRAY),
            ),
        ])
    } else {
        let mut spans = vec![
            Span::styled("> ", Style::default().fg(theme::CYAN).add_modifier(Modifier::BOLD)),
            Span::styled(&app.input[..], input_style),
        ];

        if let Some(hint) = app::tab_hint(&app.input) {
            let ghost = &hint[app.input.len()..];
            spans.push(Span::styled(ghost, Style::default().fg(theme::DARK_GRAY)));
        }

        Line::from(spans)
    };

    frame.render_widget(Paragraph::new(content), area);
}
