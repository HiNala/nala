//! Boot splash screen.
//!
//! Shown for 1.5 seconds when Nala first launches. Clean, minimal, professional.
//! Inspired by OpenCode's instant dark boot and Claude Code's terse startup style.

use crate::app::App;
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Paragraph},
    Frame,
};

/// ASCII art for the NALA wordmark.
/// Designed to be readable at narrow terminal widths (min 40 cols).
const LOGO: &str = r#"
███╗   ██╗ █████╗ ██╗      █████╗
████╗  ██║██╔══██╗██║     ██╔══██╗
██╔██╗ ██║███████║██║     ███████║
██║╚██╗██║██╔══██║██║     ██╔══██║
██║ ╚████║██║  ██║███████╗██║  ██║
╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝"#;

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    // Dark background
    frame.render_widget(
        Block::default().style(Style::default().bg(Color::Black)),
        area,
    );

    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Fill(1),
            Constraint::Length(8),  // logo
            Constraint::Length(1),  // spacer
            Constraint::Length(1),  // tagline
            Constraint::Length(1),  // version
            Constraint::Length(2),  // loading indicator
            Constraint::Fill(1),
        ])
        .split(area);

    // Logo
    let logo_text = Text::from(
        LOGO.lines()
            .map(|l| {
                Line::from(Span::styled(
                    l,
                    Style::default()
                        .fg(Color::Cyan)
                        .add_modifier(Modifier::BOLD),
                ))
            })
            .collect::<Vec<_>>(),
    );
    frame.render_widget(
        Paragraph::new(logo_text).alignment(Alignment::Center),
        vertical[1],
    );

    // Tagline
    frame.render_widget(
        Paragraph::new(Span::styled(
            "terminal-first AI coding environment",
            Style::default().fg(Color::DarkGray),
        ))
        .alignment(Alignment::Center),
        vertical[3],
    );

    // Version
    frame.render_widget(
        Paragraph::new(Span::styled(
            format!("v{}", env!("CARGO_PKG_VERSION")),
            Style::default().fg(Color::DarkGray),
        ))
        .alignment(Alignment::Center),
        vertical[4],
    );

    // Animated loading dots / progress hint
    let elapsed_ms = app.splash_start.elapsed().as_millis();
    let dot_count = ((elapsed_ms / 300) % 4) as usize;
    let dots = ".".repeat(dot_count);
    let loading_text = if let Some(progress) = app.index_progress {
        format!("indexing{} {:>3}%", dots, (progress * 100.0).round() as usize)
    } else {
        format!("indexing{}", dots)
    };
    frame.render_widget(
        Paragraph::new(Span::styled(
            loading_text,
            Style::default().fg(Color::DarkGray),
        ))
        .alignment(Alignment::Center),
        vertical[5],
    );
}
