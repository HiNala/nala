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
    let mode_color = match app.mode {
        AppMode::Ready => theme::GREEN,
        AppMode::Analyzing => theme::YELLOW,
        AppMode::Confirming => theme::YELLOW,
        _ => theme::CYAN,
    };

    let mut detail = if app.index_progress.is_some() {
        let phase = app.index_phase.as_deref().unwrap_or("indexing");
        format!(" {} {}...", SPINNER[(app.splash_start.elapsed().as_millis() / 80) as usize % SPINNER.len()], phase)
    } else if app.stats.total_files > 0 {
        format!(" {} files  {} symbols", app.stats.total_files, app.stats.total_functions)
    } else {
        format!(" {}", app.status_text)
    };

    if !app.agent_phase.is_empty()
        && app.agent_phase != "idle"
        && app.agent_phase != "done"
    {
        detail.push_str(&format!("  agent:{}", app.agent_phase.to_uppercase()));
        if !app.agent_mode.is_empty() {
            detail.push_str(&format!("[{}]", app.agent_mode.to_uppercase()));
        }
        if app.agent_checkpoint_count > 0 {
            detail.push_str(&format!(" cp:{}", app.agent_checkpoint_count));
        }
        if !app.agent_choices.is_empty() {
            detail.push_str(&format!(" ⚡{}", app.agent_choices.len()));
        }
    }

    if app.context_effective_limit > 0 && area.width >= 90 {
        let bar = context_bar(app.context_utilization_pct);
        detail.push_str(&format!(
            "  ctx {:.0}% {} {}/{}",
            app.context_utilization_pct,
            bar,
            short_tokens(app.context_total_tokens),
            short_tokens(app.context_effective_limit)
        ));
    }

    let right_text = if area.width >= 110 && !app.llm_model.is_empty() {
        format!("{}  /help", app.llm_model)
    } else if area.width >= 72 {
        "/help".to_string()
    } else {
        String::new()
    };

    let right_width = right_text.chars().count() as u16;
    let left_detail_limit = area
        .width
        .saturating_sub(right_width.saturating_add(10)) as usize;
    let detail = truncate_text(&detail, left_detail_limit);

    let cols = if right_text.is_empty() {
        Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Fill(1)])
            .split(area)
    } else {
        Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Fill(1), Constraint::Length(right_width)])
            .split(area)
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
    left_spans.push(Span::styled(detail, Style::default().fg(theme::GRAY)));

    frame.render_widget(Paragraph::new(Line::from(left_spans)), cols[0]);

    if !right_text.is_empty() {
        let right_spans = if right_text == "/help" {
            vec![Span::styled("/help", Style::default().fg(theme::CYAN))]
        } else {
            vec![
                Span::styled(
                    app.llm_model.clone(),
                    Style::default().fg(theme::GRAY),
                ),
                Span::styled("  ", Style::default()),
                Span::styled("/help", Style::default().fg(theme::CYAN)),
            ]
        };
        frame.render_widget(
            Paragraph::new(Line::from(right_spans)).alignment(ratatui::layout::Alignment::Right),
            cols[1],
        );
    }
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

fn truncate_text(text: &str, max_chars: usize) -> String {
    if max_chars == 0 {
        return String::new();
    }

    let char_count = text.chars().count();
    if char_count <= max_chars {
        return text.to_string();
    }

    if max_chars <= 3 {
        return ".".repeat(max_chars);
    }

    let keep = max_chars - 3;
    let truncated: String = text.chars().take(keep).collect();
    format!("{}...", truncated)
}
