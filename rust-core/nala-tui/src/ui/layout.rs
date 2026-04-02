//! Main layout compositor.
//!
//! Terminal-native layout: no heavy chrome, no custom backgrounds.
//! Messages flow naturally like in Claude Code / Gemini CLI.
//!
//!   ┌──────────────────────────────────────┐
//!   │  MESSAGE LOG  (scrollable)           │
//!   │  (optional side panels)              │
//!   ├──────────────────────────────────────┤
//!   │  ─── separator ───                   │
//!   │  > prompt input                      │
//!   ├──────────────────────────────────────┤
//!   │  status bar                          │
//!   └──────────────────────────────────────┘

use crate::app::{App, AppMode, MessageKind};
use crate::ui::{command_bar, diff, file_panel, session_panel, splash, status_bar, theme};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Paragraph, Wrap},
    Frame,
};

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    let outer = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Fill(1),
            Constraint::Length(2),
            Constraint::Length(1),
        ])
        .split(area);

    if app.mode == AppMode::Confirming && !app.pending_actions.is_empty() {
        diff::render_confirm(frame, app, outer[0]);
    } else {
        render_body(frame, app, outer[0]);
    }
    command_bar::render(frame, app, outer[1]);
    status_bar::render(frame, app, outer[2]);
}

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

    let main_area = cols[col_idx];
    let has_conversation = app
        .messages
        .iter()
        .any(|m| matches!(m.kind, MessageKind::User | MessageKind::Assistant))
        || app.streaming_response.is_some();

    if has_conversation {
        render_messages(frame, app, main_area);
    } else {
        splash::render(frame, app, main_area);
    }

    col_idx += 1;
    if right_open {
        session_panel::render(frame, app, cols[col_idx]);
    }
}

fn render_messages(frame: &mut Frame, app: &App, area: Rect) {
    let mut lines: Vec<Line> = Vec::new();

    for msg in &app.messages {
        match msg.kind {
            MessageKind::User => {
                lines.push(Line::from(""));
                lines.push(Line::from(vec![
                    Span::styled(
                        "  > ",
                        Style::default()
                            .fg(theme::CYAN)
                            .add_modifier(Modifier::BOLD),
                    ),
                    Span::styled(
                        msg.text.lines().next().unwrap_or(""),
                        Style::default()
                            .fg(theme::WHITE)
                            .add_modifier(Modifier::BOLD),
                    ),
                ]));
                for text_line in msg.text.lines().skip(1) {
                    lines.push(Line::from(Span::styled(
                        format!("    {}", text_line),
                        Style::default().fg(theme::WHITE),
                    )));
                }
            }
            MessageKind::Assistant => {
                lines.push(Line::from(""));
                let mut assistant_lines = msg.text.lines();
                if let Some(first_line) = assistant_lines.next() {
                    lines.push(Line::from(vec![
                        Span::styled("  ai ", theme::bold_accent()),
                        Span::styled(first_line, Style::default()),
                    ]));
                }
                for text_line in assistant_lines {
                    lines.push(Line::from(vec![
                        Span::styled("     ", Style::default().fg(theme::DARK_GRAY)),
                        Span::styled(text_line, Style::default()),
                    ]));
                }
            }
            MessageKind::System => {
                lines.push(Line::from(Span::styled(
                    format!("  {}", msg.text.lines().next().unwrap_or("")),
                    Style::default().fg(theme::DARK_GRAY),
                )));
                for text_line in msg.text.lines().skip(1) {
                    lines.push(Line::from(Span::styled(
                        format!("  {}", text_line),
                        Style::default().fg(theme::DARK_GRAY),
                    )));
                }
            }
            MessageKind::Error => {
                lines.push(Line::from(vec![
                    Span::styled(
                        "  error: ",
                        Style::default().fg(theme::RED).add_modifier(Modifier::BOLD),
                    ),
                    Span::styled(
                        msg.text.lines().next().unwrap_or(""),
                        Style::default().fg(theme::RED),
                    ),
                ]));
                for text_line in msg.text.lines().skip(1) {
                    lines.push(Line::from(Span::styled(
                        format!("         {}", text_line),
                        Style::default().fg(theme::RED),
                    )));
                }
            }
        }
    }

    if let Some(ref streaming) = app.streaming_response {
        lines.push(Line::from(""));
        let mut streaming_lines = streaming.lines();
        if let Some(first_line) = streaming_lines.next() {
            lines.push(Line::from(vec![
                Span::styled("  ai ", theme::bold_accent()),
                Span::styled(first_line, Style::default()),
            ]));
        }
        for text_line in streaming_lines {
            lines.push(Line::from(vec![
                Span::styled("     ", Style::default().fg(theme::DARK_GRAY)),
                Span::styled(text_line, Style::default()),
            ]));
        }
        lines.push(Line::from(vec![
            Span::styled("     ", Style::default().fg(theme::DARK_GRAY)),
            Span::styled("_", theme::bold_accent().add_modifier(Modifier::SLOW_BLINK)),
        ]));
    }

    let total_lines = lines.len();
    let show_scroll_hint = app.scroll_offset > 0;
    let message_area = if show_scroll_hint && area.height > 1 {
        Rect {
            x: area.x,
            y: area.y + 1,
            width: area.width,
            height: area.height - 1,
        }
    } else {
        area
    };
    let visible_height = message_area.height as usize;
    let max_offset = total_lines.saturating_sub(visible_height);
    let offset = app.scroll_offset.min(max_offset);
    let start = max_offset.saturating_sub(offset);
    let visible: Vec<Line> = lines.into_iter().skip(start).take(visible_height).collect();

    frame.render_widget(
        Paragraph::new(visible).wrap(Wrap { trim: false }),
        message_area,
    );

    if show_scroll_hint && offset > 0 {
        let hint = Line::from(Span::styled(
            format!("  ── {} more lines (PgUp to scroll) ──", offset),
            Style::default().fg(theme::DARK_GRAY),
        ));
        frame.render_widget(
            Paragraph::new(hint),
            Rect {
                x: area.x,
                y: area.y,
                width: area.width,
                height: 1,
            },
        );
    }
}
