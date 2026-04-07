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
        Style::default().fg(theme::BORDER),
    ));
    frame.render_widget(Paragraph::new(separator), rows[0]);

    let is_slash = app.input.starts_with('/');

    let input_style = if is_slash {
        Style::default()
            .fg(theme::ACCENT)
            .bg(theme::USER_INPUT_BG)
    } else {
        Style::default()
            .fg(theme::WHITE)
            .bg(theme::USER_INPUT_BG)
    };

    let prompt_text = " nala ❯ ";
    let prompt_width = prompt_text.chars().count();
    let available_text = area.width.saturating_sub(prompt_width as u16) as usize;

    let content = if app.input.is_empty() {
        Line::from(vec![
            Span::styled(
                prompt_text,
                Style::default()
                    .fg(theme::ACCENT)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                truncate_text("Type a question, use /agent <id>, or press ? for help", available_text),
                Style::default().fg(theme::GRAY),
            ),
        ])
    } else {
        let visible_input = tail_fit(&app.input, available_text);
        let mut spans = vec![
            Span::styled(
                prompt_text,
                Style::default()
                    .fg(theme::ACCENT)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(visible_input, input_style),
        ];

        if let Some(hint) = app::tab_hint(&app.input) {
            if let Some(ghost) = hint.get(app.input.len()..) {
                let remaining = available_text.saturating_sub(app.input.chars().count());
                if remaining > 0 {
                    spans.push(Span::styled(
                        truncate_text(ghost, remaining),
                        Style::default().fg(theme::GRAY),
                    ));
                }
            }
        }

        Line::from(spans)
    };

    frame.render_widget(Paragraph::new(content), rows[1]);
}

fn truncate_text(text: &str, max_chars: usize) -> String {
    if max_chars == 0 {
        return String::new();
    }
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    if max_chars <= 3 {
        return ".".repeat(max_chars);
    }
    let kept: String = text.chars().take(max_chars - 3).collect();
    format!("{kept}...")
}

fn tail_fit(text: &str, max_chars: usize) -> String {
    if max_chars == 0 {
        return String::new();
    }
    let chars: Vec<char> = text.chars().collect();
    if chars.len() <= max_chars {
        return text.to_string();
    }
    if max_chars <= 3 {
        return ".".repeat(max_chars);
    }
    let kept: String = chars[chars.len() - (max_chars - 3)..].iter().collect();
    format!("...{kept}")
}
