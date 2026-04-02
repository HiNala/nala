//! Boot splash screen.
//!
//! Shown for ~1.5 seconds on launch. Clean and minimal — sets the
//! professional tone described in Mission 04 and the Master Plan.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Gauge, Paragraph},
    Frame,
};

const LOGO: &str = r"
  ╦ ╦ ╦ ╔╗╔ ╔═╗ ╦   ╔═╗
  ╠═╣ ║ ║║║ ╠═╣ ║   ╠═╣
  ╩ ╩ ╩ ╝╚╝ ╩ ╩ ╩═╝ ╩ ╩";

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    frame.render_widget(
        Block::default().style(Style::default().bg(theme::BG_DEEP)),
        area,
    );

    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Fill(1),
            Constraint::Length(4),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Length(3),
            Constraint::Fill(1),
        ])
        .split(area);

    // Logo — gradient-style accent
    let logo_lines: Vec<Line> = LOGO
        .lines()
        .enumerate()
        .map(|(i, l)| {
            let color = match i {
                0 | 1 => theme::ACCENT_PRIMARY,
                2 => theme::ACCENT_SECONDARY,
                _ => theme::FG_MUTED,
            };
            Line::from(Span::styled(
                l,
                Style::default().fg(color).add_modifier(Modifier::BOLD),
            ))
        })
        .collect();
    frame.render_widget(
        Paragraph::new(logo_lines).alignment(Alignment::Center),
        vertical[1],
    );

    // Tagline
    frame.render_widget(
        Paragraph::new(Span::styled(
            "terminal-first AI coding environment",
            Style::default().fg(theme::FG_MUTED),
        ))
        .alignment(Alignment::Center),
        vertical[3],
    );

    // Version
    frame.render_widget(
        Paragraph::new(Span::styled(
            format!("v{}", env!("CARGO_PKG_VERSION")),
            Style::default().fg(theme::FG_DIM),
        ))
        .alignment(Alignment::Center),
        vertical[4],
    );

    // Progress gauge
    let progress = app.index_progress.unwrap_or(0.0);
    let elapsed_ms = app.splash_start.elapsed().as_millis();
    let dots = ".".repeat(((elapsed_ms / 400) % 4) as usize);
    let label = format!("initializing{}", dots);

    let gauge_area = centered_rect(40, vertical[6]);
    frame.render_widget(
        Gauge::default()
            .block(Block::default())
            .gauge_style(
                Style::default()
                    .fg(theme::GAUGE_FILLED)
                    .bg(theme::GAUGE_EMPTY),
            )
            .ratio(progress.clamp(0.0, 1.0))
            .label(Span::styled(label, Style::default().fg(theme::FG_MUTED))),
        gauge_area,
    );
}

fn centered_rect(percent_x: u16, r: ratatui::layout::Rect) -> ratatui::layout::Rect {
    let pad = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(r);
    pad[1]
}
