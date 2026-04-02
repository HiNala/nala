//! Status bar — single-line footer with mode, project stats, and key hints.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Fill(1), Constraint::Min(46)])
        .split(area);

    let stats = if app.stats.total_files > 0 {
        let base = format!(
            " {} files · {} symbols",
            app.stats.total_files, app.stats.total_functions
        );
        if let Some(p) = app.index_progress {
            format!("{} · indexing {:>3}%", base, (p * 100.0).round() as usize)
        } else {
            base
        }
    } else {
        app.status_text.clone()
    };

    let mode_color = match &*format!("{}", app.mode) {
        "READY" | "COMMAND" => theme::ACCENT_GREEN,
        "ANALYZING" => theme::ACCENT_WARM,
        "CONFIRM" => theme::WARNING,
        _ => theme::ACCENT_PRIMARY,
    };

    let left = Line::from(vec![
        Span::styled(
            format!(" {} ", app.mode),
            Style::default()
                .bg(mode_color)
                .fg(theme::BG_DEEP)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!(" {}", stats),
            Style::default().fg(theme::FG_SECONDARY),
        ),
    ]);

    frame.render_widget(
        Paragraph::new(left).style(Style::default().bg(theme::BG_SURFACE)),
        cols[0],
    );

    let hints = Line::from(vec![
        Span::styled(
            "^B",
            Style::default()
                .fg(theme::ACCENT_PRIMARY)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" files ", Style::default().fg(theme::FG_DIM)),
        Span::styled(
            "^E",
            Style::default()
                .fg(theme::ACCENT_PRIMARY)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" sessions ", Style::default().fg(theme::FG_DIM)),
        Span::styled(
            "/help",
            Style::default()
                .fg(theme::ACCENT_PRIMARY)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled("  ", Style::default()),
    ]);

    frame.render_widget(
        Paragraph::new(hints).style(Style::default().bg(theme::BG_SURFACE)),
        cols[1],
    );
}
