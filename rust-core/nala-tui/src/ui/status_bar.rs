//! Status bar — single-line footer with mode, project stats, and key hints.

use crate::app::App;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Fill(1), Constraint::Min(50)])
        .split(area);

    // Left: mode + stats
    let stats = if app.stats.total_files > 0 {
        format!(
            " {} files · {} symbols",
            app.stats.total_files, app.stats.total_functions
        )
    } else {
        app.status_text.clone()
    };

    let left = Line::from(vec![
        Span::styled(
            format!(" {} ", app.mode),
            Style::default()
                .bg(Color::Cyan)
                .fg(Color::Black)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!(" {}", stats),
            Style::default().fg(Color::DarkGray),
        ),
    ]);

    frame.render_widget(
        Paragraph::new(left).style(Style::default().bg(Color::Rgb(15, 15, 25))),
        cols[0],
    );

    // Right: keyboard shortcut hints
    let hints = Line::from(vec![
        Span::styled("Ctrl+B", Style::default().fg(Color::DarkGray).add_modifier(Modifier::BOLD)),
        Span::styled(": files  ", Style::default().fg(Color::Rgb(50, 50, 70))),
        Span::styled("Ctrl+E", Style::default().fg(Color::DarkGray).add_modifier(Modifier::BOLD)),
        Span::styled(": sessions  ", Style::default().fg(Color::Rgb(50, 50, 70))),
        Span::styled("/help", Style::default().fg(Color::DarkGray).add_modifier(Modifier::BOLD)),
        Span::styled("  ", Style::default()),
    ]);

    frame.render_widget(
        Paragraph::new(hints).style(Style::default().bg(Color::Rgb(15, 15, 25))),
        cols[1],
    );
}
