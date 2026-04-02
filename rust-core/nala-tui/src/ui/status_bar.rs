//! Status bar — single line at the very bottom.
//! Shows: mode | stats or status | model info | shortcuts

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
        .constraints([Constraint::Fill(1), Constraint::Min(40)])
        .split(area);

    let mode_color = match app.mode {
        AppMode::Ready => theme::GREEN,
        AppMode::Analyzing => theme::YELLOW,
        AppMode::Confirming => theme::YELLOW,
        _ => theme::CYAN,
    };

    let mut left_spans: Vec<Span> = vec![Span::styled(
        format!(" {} ", app.mode),
        Style::default()
            .fg(mode_color)
            .add_modifier(Modifier::BOLD),
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
            format!(
                " {} files  {} symbols",
                app.stats.total_files, app.stats.total_functions
            ),
            Style::default().fg(theme::GRAY),
        ));
    } else {
        left_spans.push(Span::styled(
            format!(" {}", app.status_text),
            Style::default().fg(theme::GRAY),
        ));
    }

    if app.context_effective_limit > 0 {
        let ctx_color = if app.context_utilization_pct < 60.0 {
            theme::GREEN
        } else if app.context_utilization_pct < 80.0 {
            theme::YELLOW
        } else {
            theme::RED
        };
        let bar = context_bar(app.context_utilization_pct);
        left_spans.push(Span::styled("  ctx ", Style::default().fg(theme::GRAY)));
        left_spans.push(Span::styled(
            format!("{:.0}% ", app.context_utilization_pct),
            Style::default().fg(ctx_color).add_modifier(Modifier::BOLD),
        ));
        left_spans.push(Span::styled(
            format!("{} ", bar),
            Style::default().fg(ctx_color),
        ));
        left_spans.push(Span::styled(
            format!(
                "{}/{}",
                short_tokens(app.context_total_tokens),
                short_tokens(app.context_effective_limit)
            ),
            Style::default().fg(theme::GRAY),
        ));
    }

    frame.render_widget(Paragraph::new(Line::from(left_spans)), cols[0]);

    let mut right_spans: Vec<Span> = Vec::new();

    if !app.llm_model.is_empty() {
        right_spans.push(Span::styled(
            app.llm_model.clone(),
            Style::default().fg(theme::GRAY),
        ));
        right_spans.push(Span::styled("  ", Style::default()));
    }

    right_spans.push(Span::styled(
        "/help",
        Style::default().fg(theme::CYAN),
    ));
    right_spans.push(Span::styled(" ", Style::default()));

    let hints = Line::from(right_spans);
    frame.render_widget(
        Paragraph::new(hints).alignment(ratatui::layout::Alignment::Right),
        cols[1],
    );
}

fn context_bar(utilization_pct: f64) -> String {
    let filled = ((utilization_pct / 10.0).round() as usize).min(10);
    let empty = 10usize.saturating_sub(filled);
    format!("[{}{}]", "█".repeat(filled), "░".repeat(empty))
}

fn short_tokens(tokens: usize) -> String {
    if tokens >= 1_000_000 {
        format!("{:.1}m", tokens as f64 / 1_000_000.0)
    } else if tokens >= 1_000 {
        format!("{:.0}k", tokens as f64 / 1_000.0)
    } else {
        tokens.to_string()
    }
}
