//! Status bar — single-line footer with mode, project stats, spinner, and key hints.

use crate::app::{App, AppMode};
use crate::ui::theme;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

const SPINNER: &[&str] = &["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Fill(1), Constraint::Min(52)])
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
        format!(" {}", app.status_text)
    };

    let mode_color = match app.mode {
        AppMode::Ready | AppMode::Command => theme::ACCENT_GREEN,
        AppMode::Analyzing => theme::ACCENT_WARM,
        AppMode::Confirming => theme::WARNING,
        _ => theme::ACCENT_PRIMARY,
    };

    let mut left_spans: Vec<Span> = vec![
        Span::styled(
            format!(" {} ", app.mode),
            Style::default()
                .bg(mode_color)
                .fg(theme::BG_DEEP)
                .add_modifier(Modifier::BOLD),
        ),
    ];

    if app.mode == AppMode::Analyzing {
        let idx = (app.splash_start.elapsed().as_millis() / 80) as usize % SPINNER.len();
        left_spans.push(Span::styled(
            format!(" {} ", SPINNER[idx]),
            Style::default().fg(theme::ACCENT_WARM),
        ));
    }

    left_spans.push(Span::styled(stats, Style::default().fg(theme::FG_SECONDARY)));

    let uptime = app.splash_start.elapsed().as_secs();
    let uptime_str = if uptime >= 3600 {
        format!("{}h{}m", uptime / 3600, (uptime % 3600) / 60)
    } else if uptime >= 60 {
        format!("{}m{}s", uptime / 60, uptime % 60)
    } else {
        format!("{}s", uptime)
    };

    left_spans.push(Span::styled(
        format!(" · {}", uptime_str),
        Style::default().fg(theme::FG_DIM),
    ));

    frame.render_widget(
        Paragraph::new(Line::from(left_spans))
            .style(Style::default().bg(theme::BG_SURFACE)),
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
            "PgUp/Dn",
            Style::default()
                .fg(theme::ACCENT_PRIMARY)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" scroll ", Style::default().fg(theme::FG_DIM)),
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
