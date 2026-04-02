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

    let stats = if app.stats.total_files > 0 {
        let base = format!(
            " {} files · {} symbols",
            app.stats.total_files, app.stats.total_functions
        );
        let with_progress = if let Some(p) = app.index_progress {
            format!("{} · indexing {:>3}%", base, (p * 100.0).round() as usize)
        } else {
            base
        };
        let errors = app.diagnostics_store.error_count();
        let warnings = app.diagnostics_store.warning_count();
        if errors > 0 || warnings > 0 {
            format!("{} · E:{} W:{}", with_progress, errors, warnings)
        } else {
            with_progress
        }
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
