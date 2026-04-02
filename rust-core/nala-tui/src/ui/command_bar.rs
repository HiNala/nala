//! Command input bar.
//!
//! The primary interaction point. Sits at the bottom of the screen above the
//! status bar. Renders a prompt prefix, the current input text, and a blinking
//! cursor. Slash commands are highlighted differently from free-text queries.

use crate::app::App;
use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let is_slash = app.input.starts_with('/');

    let input_style = if is_slash {
        Style::default().fg(Color::Yellow)
    } else {
        Style::default().fg(Color::White)
    };

    let prompt = Span::styled(
        "  ❯ ",
        Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
    );

    // Split at cursor to insert the cursor block
    let before_cursor = &app.input[..app.cursor_pos];
    let after_cursor = &app.input[app.cursor_pos..];

    // Get the character under the cursor (or space if at end)
    let (cursor_char, rest) = if after_cursor.is_empty() {
        (" ", "")
    } else {
        let mut chars = after_cursor.char_indices();
        let ch = match chars.next() {
            Some((_, c)) => c,
            None => return, // should not happen after is_empty guard
        };
        let end = ch.len_utf8();
        (&after_cursor[..end], &after_cursor[end..])
    };

    let line = Line::from(vec![
        prompt,
        Span::styled(before_cursor, input_style),
        Span::styled(
            cursor_char,
            Style::default()
                .bg(Color::Cyan)
                .fg(Color::Black)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(rest, input_style),
    ]);

    let hint = if app.input.is_empty() {
        "  Type a question or /help for commands"
    } else {
        ""
    };

    let content = if app.input.is_empty() {
        Line::from(vec![
            Span::styled("  ❯ ", Style::default().fg(Color::Rgb(60, 60, 80)).add_modifier(Modifier::BOLD)),
            Span::styled(hint, Style::default().fg(Color::Rgb(60, 60, 80))),
        ])
    } else {
        line
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Rgb(40, 40, 80)))
        .style(Style::default().bg(Color::Rgb(12, 12, 22)));

    frame.render_widget(
        Paragraph::new(content).block(block),
        area,
    );
}
