//! Main layout compositor.
//!
//! Assembles all panels and widgets into the full-screen layout.
//! This is purely a rendering function — no state mutation happens here.
//!
//! Layout structure:
//!   ┌─────────────────────────────────────────────┐
//!   │ TOP BAR  (brand · project · git · LSP · mode)│
//!   ├──────────┬──────────────────────┬────────────┤
//!   │ FILE     │                      │ SESSION    │
//!   │ PANEL    │  MAIN CONTENT AREA   │ PANEL      │
//!   │ (opt)    │  (message log)       │ (opt)      │
//!   ├──────────┴──────────────────────┴────────────┤
//!   │ COMMAND INPUT BAR                            │
//!   ├─────────────────────────────────────────────┤
//!   │ STATUS BAR                                  │
//!   └─────────────────────────────────────────────┘

use crate::app::{App, AppMode, MessageKind};
use crate::ui::{command_bar, diff, file_panel, session_panel, status_bar, theme};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Scrollbar, ScrollbarOrientation, ScrollbarState, Wrap},
    Frame,
};

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    let outer = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Fill(1),
            Constraint::Length(3),
            Constraint::Length(1),
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

    let git_branch = detect_git_branch(&app.project_root);

    let mode_color = match app.mode {
        AppMode::Booting => theme::FG_DIM,
        AppMode::Ready | AppMode::Command => theme::ACCENT_GREEN,
        AppMode::Analyzing => theme::ACCENT_WARM,
        AppMode::Viewing => theme::ACCENT_PRIMARY,
        AppMode::Confirming => theme::WARNING,
    };

    let mut spans = vec![
        Span::styled(
            " ◆ HiNala ",
            Style::default()
                .fg(theme::BG_DEEP)
                .bg(theme::ACCENT_PRIMARY)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" ", Style::default().bg(theme::BG_SURFACE)),
        Span::styled(
            format!(" {} ", project_name),
            Style::default()
                .fg(theme::FG_PRIMARY)
                .bg(theme::BG_SURFACE),
        ),
    ];

    if let Some(ref branch) = git_branch {
        spans.push(Span::styled(
            " ⎇ ",
            Style::default()
                .fg(theme::FG_DIM)
                .bg(theme::BG_SURFACE),
        ));
        spans.push(Span::styled(
            format!("{} ", branch),
            Style::default()
                .fg(theme::ACCENT_SECONDARY)
                .bg(theme::BG_SURFACE),
        ));
    }

    if app.lsp_initialized {
        let errors = app.diagnostics_store.error_count();
        let warnings = app.diagnostics_store.warning_count();
        if errors > 0 || warnings > 0 {
            let diag_text = format!(" E:{} W:{} ", errors, warnings);
            let diag_color = if errors > 0 {
                theme::ERROR
            } else {
                theme::WARNING
            };
            spans.push(Span::styled(
                diag_text,
                Style::default().fg(diag_color).bg(theme::BG_SURFACE),
            ));
        } else {
            spans.push(Span::styled(
                " LSP ● ",
                Style::default()
                    .fg(theme::ACCENT_GREEN)
                    .bg(theme::BG_SURFACE),
            ));
        }
    }

    // Right-aligned mode badge
    let mode_text = format!(" {} ", app.mode);
    let used_width: usize = spans.iter().map(|s| s.width()).sum();
    let remaining = area.width as usize - used_width.min(area.width as usize);
    let padding = remaining.saturating_sub(mode_text.len() + 1);

    spans.push(Span::styled(
        " ".repeat(padding),
        Style::default().bg(theme::BG_SURFACE),
    ));
    spans.push(Span::styled(
        mode_text,
        Style::default()
            .fg(theme::BG_DEEP)
            .bg(mode_color)
            .add_modifier(Modifier::BOLD),
    ));

    let line = Line::from(spans);
    frame.render_widget(
        Paragraph::new(line).style(Style::default().bg(theme::BG_SURFACE)),
        area,
    );
}

fn detect_git_branch(root: &std::path::Path) -> Option<String> {
    let head = root.join(".git").join("HEAD");
    let contents = std::fs::read_to_string(head).ok()?;
    let trimmed = contents.trim();
    if let Some(rest) = trimmed.strip_prefix("ref: refs/heads/") {
        Some(rest.to_string())
    } else {
        Some(trimmed[..8.min(trimmed.len())].to_string())
    }
}

// ── Body ───────────────────────────────────────────────────────────────────

fn render_body(frame: &mut Frame, app: &App, area: Rect) {
    let left_open = app.panels.file_panel_open;
    let right_open = app.panels.session_panel_open;

    let constraints = match (left_open, right_open) {
        (true, true) => vec![
            Constraint::Length(30),
            Constraint::Fill(1),
            Constraint::Length(28),
        ],
        (true, false) => vec![Constraint::Length(30), Constraint::Fill(1)],
        (false, true) => vec![Constraint::Fill(1), Constraint::Length(28)],
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
    let block = Block::default()
        .borders(Borders::LEFT | Borders::RIGHT)
        .border_style(Style::default().fg(theme::BORDER_DIM))
        .style(theme::base_style());

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let mut lines: Vec<Line> = Vec::new();

    for msg in &app.messages {
        let (badge, badge_style, text_style) = match msg.kind {
            MessageKind::User => (
                " YOU ",
                theme::badge_style(theme::ACCENT_PRIMARY, theme::BG_DEEP),
                Style::default().fg(theme::MSG_USER),
            ),
            MessageKind::Assistant => (
                " AI  ",
                theme::badge_style(theme::ACCENT_SECONDARY, theme::BG_DEEP),
                Style::default().fg(theme::MSG_ASSISTANT),
            ),
            MessageKind::System => (
                " SYS ",
                theme::badge_style(theme::BG_ELEVATED, theme::FG_MUTED),
                Style::default().fg(theme::MSG_SYSTEM),
            ),
            MessageKind::Error => (
                " ERR ",
                theme::badge_style(theme::ERROR, theme::BG_DEEP),
                Style::default().fg(theme::MSG_ERROR),
            ),
        };

        for (i, text_line) in msg.text.lines().enumerate() {
            if i == 0 {
                lines.push(Line::from(vec![
                    Span::styled(badge, badge_style),
                    Span::styled(
                        format!(" {}", text_line),
                        text_style,
                    ),
                ]));
            } else {
                lines.push(Line::from(Span::styled(
                    format!("      {}", text_line),
                    text_style,
                )));
            }
        }
        // Thin visual separator between messages
        lines.push(Line::from(Span::styled(
            "─".repeat(inner.width.saturating_sub(2) as usize),
            Style::default().fg(theme::BORDER_DIM),
        )));
    }

    // Streaming response
    if let Some(ref streaming) = app.streaming_response {
        lines.push(Line::from(vec![
            Span::styled(
                " AI  ",
                theme::badge_style(theme::ACCENT_SECONDARY, theme::BG_DEEP),
            ),
            Span::styled(" ", Style::default().fg(theme::MSG_ASSISTANT)),
        ]));
        for text_line in streaming.lines() {
            lines.push(Line::from(Span::styled(
                format!("      {}", text_line),
                Style::default().fg(theme::MSG_ASSISTANT),
            )));
        }
        lines.push(Line::from(Span::styled(
            "      ▋",
            Style::default()
                .fg(theme::ACCENT_PRIMARY)
                .add_modifier(Modifier::SLOW_BLINK),
        )));
    }

    // Scroll to bottom
    let total_lines = lines.len();
    let visible_height = inner.height as usize;
    let start = total_lines.saturating_sub(visible_height);
    let visible: Vec<Line> = lines.into_iter().skip(start).collect();

    frame.render_widget(
        Paragraph::new(visible)
            .wrap(Wrap { trim: false })
            .style(theme::base_style()),
        inner,
    );

    // Scrollbar on the right edge
    if total_lines > visible_height {
        let mut scrollbar_state =
            ScrollbarState::new(total_lines).position(start);
        frame.render_stateful_widget(
            Scrollbar::new(ScrollbarOrientation::VerticalRight)
                .thumb_style(Style::default().fg(theme::FG_DIM))
                .track_style(Style::default().fg(theme::BORDER_DIM)),
            area,
            &mut scrollbar_state,
        );
    }
}
