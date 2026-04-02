//! Status bar -- single line at the very bottom.
//! Minimal: mode indicator, stats, key hints. Terminal-native colors.

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
        .constraints([Constraint::Fill(1), Constraint::Min(32)])
        .split(area);

    let mode_color = match app.mode {
        AppMode::Ready | AppMode::Command => theme::GREEN,
        AppMode::Analyzing => theme::YELLOW,
        AppMode::Confirming => theme::YELLOW,
        _ => theme::CYAN,
    };

    let mut left_spans: Vec<Span> = vec![Span::styled(
        format!(" {} ", app.mode),
        Style::default().fg(mode_color).add_modifier(Modifier::BOLD),
    )];

    if app.mode == AppMode::Analyzing {
        let idx = (app.splash_start.elapsed().as_millis() / 80) as usize % SPINNER.len();
        left_spans.push(Span::styled(
            format!("{} ", SPINNER[idx]),
            Style::default().fg(theme::YELLOW),
        ));
    }

    if app.stats.total_files > 0 {
        left_spans.push(Span::styled(
            format!("· {} files · {} symbols", app.stats.total_files, app.stats.total_functions),
            Style::default().fg(theme::DARK_GRAY),
        ));
    } else {
        left_spans.push(Span::styled(
            format!("· {}", app.status_text),
            Style::default().fg(theme::DARK_GRAY),
        ));
    }

    frame.render_widget(Paragraph::new(Line::from(left_spans)), cols[0]);

    let hints = Line::from(vec![
        Span::styled("? ", Style::default().fg(theme::DARK_GRAY)),
        Span::styled("for shortcuts", Style::default().fg(theme::DARK_GRAY)),
        Span::styled("  · ", Style::default().fg(theme::DARK_GRAY)),
        Span::styled("/help", Style::default().fg(theme::CYAN)),
        Span::styled(" ", Style::default()),
    ]);

    frame.render_widget(Paragraph::new(hints), cols[1]);
}
