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

const LOGO: &[&str] = &[
    "  ╦ ╦ ╦ ╔╗╔ ╔═╗ ╦   ╔═╗",
    "  ╠═╣ ║ ║║║ ╠═╣ ║   ╠═╣",
    "  ╩ ╩ ╩ ╝╚╝ ╩ ╩ ╩═╝ ╩ ╩",
];

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
            Constraint::Length(3),
            Constraint::Length(2),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Length(2),
            Constraint::Length(3),
            Constraint::Fill(1),
        ])
        .split(area);

    let elapsed_ms = app.splash_start.elapsed().as_millis() as f64;
    let fade_factor = (elapsed_ms / 500.0).min(1.0);

    let logo_lines: Vec<Line> = LOGO
        .iter()
        .enumerate()
        .map(|(i, l)| {
            let base_color = match i {
                0 => theme::ACCENT_PRIMARY,
                1 => theme::ACCENT_SECONDARY,
                _ => theme::ACCENT_WARM,
            };
            let r = match base_color {
                ratatui::style::Color::Rgb(r, _, _) => (r as f64 * fade_factor) as u8,
                _ => 100,
            };
            let g = match base_color {
                ratatui::style::Color::Rgb(_, g, _) => (g as f64 * fade_factor) as u8,
                _ => 100,
            };
            let b = match base_color {
                ratatui::style::Color::Rgb(_, _, b) => (b as f64 * fade_factor) as u8,
                _ => 100,
            };
            Line::from(Span::styled(
                *l,
                Style::default()
                    .fg(ratatui::style::Color::Rgb(r, g, b))
                    .add_modifier(Modifier::BOLD),
            ))
        })
        .collect();
    frame.render_widget(
        Paragraph::new(logo_lines).alignment(Alignment::Center),
        vertical[1],
    );

    frame.render_widget(
        Paragraph::new(Span::styled(
            "terminal-first AI coding environment",
            Style::default().fg(theme::FG_MUTED),
        ))
        .alignment(Alignment::Center),
        vertical[3],
    );

    frame.render_widget(
        Paragraph::new(Span::styled(
            format!("v{}", env!("CARGO_PKG_VERSION")),
            Style::default().fg(theme::FG_DIM),
        ))
        .alignment(Alignment::Center),
        vertical[4],
    );

    let progress = app.index_progress.unwrap_or(0.0);
    let dots = ".".repeat(((elapsed_ms as u128 / 400) % 4) as usize);
    let label = format!("initializing{}", dots);

    let gauge_area = centered_rect(36, vertical[6]);
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
