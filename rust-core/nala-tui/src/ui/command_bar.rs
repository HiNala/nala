//! Command input bar.
//!
//! The primary interaction point. Sits at the bottom of the screen above the
//! status bar. Renders a prompt prefix, the current input text, a styled
//! cursor, and ghost-text tab-completion hints for slash commands.

use crate::app::{self, App};
use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let is_slash = app.input.starts_with('/');

    let input_style = if is_slash {
        Style::default().fg(theme::ACCENT_WARM)
    } else {
        Style::default().fg(theme::FG_PRIMARY)
    };

    let prompt_style = if app.input.is_empty() {
        Style::default()
            .fg(theme::FG_DIM)
            .add_modifier(Modifier::BOLD)
    } else {
        Style::default()
            .fg(theme::ACCENT_PRIMARY)
            .add_modifier(Modifier::BOLD)
    };

    let prompt = Span::styled("  ❯ ", prompt_style);

    let content = if app.input.is_empty() {
        Line::from(vec![
            prompt,
            Span::styled(
                "Type a question or /help for commands",
                Style::default().fg(theme::FG_DIM),
            ),
        ])
    } else {
        let before_cursor = &app.input[..app.cursor_pos];
        let after_cursor = &app.input[app.cursor_pos..];

        let (cursor_char, rest) = if after_cursor.is_empty() {
            (" ", "")
        } else {
            let ch = match after_cursor.chars().next() {
                Some(c) => c,
                None => return,
            };
            let end = ch.len_utf8();
            (&after_cursor[..end], &after_cursor[end..])
        };

        let mut spans = vec![
            prompt,
            Span::styled(before_cursor, input_style),
            Span::styled(
                cursor_char,
                Style::default()
                    .bg(theme::ACCENT_PRIMARY)
                    .fg(theme::BG_DEEP)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(rest, input_style),
        ];

        if let Some(hint) = app::tab_hint(&app.input) {
            let ghost = &hint[app.input.len()..];
            spans.push(Span::styled(
                ghost,
                Style::default().fg(theme::FG_DIM),
            ));
            spans.push(Span::styled(
                "  TAB",
                Style::default()
                    .fg(theme::BG_OVERLAY)
                    .add_modifier(Modifier::ITALIC),
            ));
        }

        Line::from(spans)
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(ratatui::widgets::BorderType::Rounded)
        .border_style(Style::default().fg(if app.input.is_empty() {
            theme::BORDER_NORMAL
        } else {
            theme::BORDER_FOCUSED
        }))
        .style(Style::default().bg(theme::BG_BASE));

    frame.render_widget(Paragraph::new(content).block(block), area);
}
