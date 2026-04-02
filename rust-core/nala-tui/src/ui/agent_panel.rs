//! Agent workbench panel — toggleable with Ctrl+G.
//!
//! Shows the current /agent run state: objective, phase, plan steps,
//! scope, verification summary, and autonomy mode.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, Padding},
    Frame,
};

fn phase_color(phase: &str) -> ratatui::style::Color {
    match phase {
        "idle" | "done" => theme::GREEN,
        "planning" | "scoping" => theme::CYAN,
        "awaiting_approval" => theme::YELLOW,
        "executing" => theme::MAGENTA,
        "verifying" | "reviewing" => theme::BLUE,
        "blocked" | "cancelled" => theme::RED,
        _ => theme::GRAY,
    }
}

fn mode_label(mode: &str) -> &str {
    match mode {
        "observe" => "OBSERVE",
        "plan" => "PLAN",
        "patch" => "PATCH",
        "autonomous" => "AUTO",
        _ => "PLAN",
    }
}

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(
            " agent ",
            Style::default()
                .fg(theme::MAGENTA)
                .add_modifier(Modifier::BOLD),
        ))
        .borders(Borders::LEFT)
        .border_style(Style::default().fg(theme::GRAY))
        .padding(Padding::new(1, 1, 0, 0));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    if inner.width < 10 || inner.height < 4 {
        return;
    }

    let max_lines = inner.height as usize;
    let max_w = inner.width as usize;
    let mut items: Vec<ListItem> = Vec::with_capacity(max_lines);

    if app.agent_phase.is_empty() || app.agent_phase == "idle" {
        items.push(ListItem::new(Line::from(Span::styled(
            "No active agent run",
            Style::default().fg(theme::GRAY),
        ))));
        items.push(ListItem::new(Line::from("")));
        items.push(ListItem::new(Line::from(Span::styled(
            "Run /agent <goal> to start",
            Style::default().fg(theme::GRAY),
        ))));
        items.push(ListItem::new(Line::from(Span::styled(
            "Ctrl+G to close panel",
            Style::default().fg(theme::GRAY),
        ))));
    } else {
        let phase_c = phase_color(&app.agent_phase);
        items.push(ListItem::new(Line::from(vec![
            Span::styled(
                "PHASE ",
                Style::default()
                    .fg(theme::GRAY)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                app.agent_phase.to_uppercase(),
                Style::default().fg(phase_c).add_modifier(Modifier::BOLD),
            ),
        ])));

        items.push(ListItem::new(Line::from(vec![
            Span::styled(
                "MODE  ",
                Style::default()
                    .fg(theme::GRAY)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                mode_label(&app.agent_mode),
                Style::default().fg(theme::CYAN),
            ),
        ])));

        items.push(ListItem::new(Line::from("")));

        if !app.agent_objective.is_empty() {
            items.push(ListItem::new(Line::from(Span::styled(
                "Objective:",
                Style::default()
                    .fg(theme::WHITE)
                    .add_modifier(Modifier::BOLD),
            ))));
            let obj = truncate(&app.agent_objective, max_w);
            items.push(ListItem::new(Line::from(Span::styled(
                obj,
                Style::default().fg(theme::WHITE),
            ))));
            items.push(ListItem::new(Line::from("")));
        }

        if !app.agent_scope.is_empty() {
            items.push(ListItem::new(Line::from(Span::styled(
                "Scope:",
                Style::default()
                    .fg(theme::WHITE)
                    .add_modifier(Modifier::BOLD),
            ))));
            for s_line in app.agent_scope.lines().take(4) {
                items.push(ListItem::new(Line::from(Span::styled(
                    truncate(s_line, max_w),
                    Style::default().fg(theme::GRAY),
                ))));
            }
            items.push(ListItem::new(Line::from("")));
        }

        if !app.agent_plan_steps.is_empty() {
            items.push(ListItem::new(Line::from(Span::styled(
                "Plan:",
                Style::default()
                    .fg(theme::WHITE)
                    .add_modifier(Modifier::BOLD),
            ))));
            for (i, step) in app.agent_plan_steps.iter().enumerate() {
                if items.len() >= max_lines.saturating_sub(3) {
                    items.push(ListItem::new(Line::from(Span::styled(
                        format!("  ... +{} more", app.agent_plan_steps.len() - i),
                        Style::default().fg(theme::GRAY),
                    ))));
                    break;
                }
                let prefix = format!("  {}. ", i + 1);
                let text = truncate(step, max_w.saturating_sub(prefix.len()));
                items.push(ListItem::new(Line::from(vec![
                    Span::styled(prefix, Style::default().fg(theme::GRAY)),
                    Span::styled(text, Style::default().fg(theme::WHITE)),
                ])));
            }
            items.push(ListItem::new(Line::from("")));
        }

        if !app.agent_verification_summary.is_empty() {
            items.push(ListItem::new(Line::from(Span::styled(
                "Verification:",
                Style::default()
                    .fg(theme::WHITE)
                    .add_modifier(Modifier::BOLD),
            ))));
            for v_line in app.agent_verification_summary.lines().take(5) {
                items.push(ListItem::new(Line::from(Span::styled(
                    truncate(v_line, max_w),
                    Style::default().fg(theme::GRAY),
                ))));
            }
            items.push(ListItem::new(Line::from("")));
        }

        if !app.agent_workers.is_empty() {
            items.push(ListItem::new(Line::from(Span::styled(
                "Workers:",
                Style::default()
                    .fg(theme::WHITE)
                    .add_modifier(Modifier::BOLD),
            ))));
            for wline in app.agent_workers.iter().take(6) {
                items.push(ListItem::new(Line::from(Span::styled(
                    truncate(wline, max_w),
                    Style::default().fg(theme::CYAN),
                ))));
            }
            if app.agent_workers.len() > 6 {
                items.push(ListItem::new(Line::from(Span::styled(
                    format!("  +{} more", app.agent_workers.len() - 6),
                    Style::default().fg(theme::GRAY),
                ))));
            }
            items.push(ListItem::new(Line::from("")));
        }

        if app.agent_checkpoint_count > 0 {
            items.push(ListItem::new(Line::from(Span::styled(
                format!("Checkpoints: {}", app.agent_checkpoint_count),
                Style::default().fg(theme::GRAY),
            ))));
        }

        if !app.agent_choices.is_empty() && items.len() < max_lines.saturating_sub(4) {
            items.push(ListItem::new(Line::from("")));
            items.push(ListItem::new(Line::from(Span::styled(
                "Next:",
                Style::default()
                    .fg(theme::YELLOW)
                    .add_modifier(Modifier::BOLD),
            ))));
            for choice in app.agent_choices.iter().take(4) {
                if items.len() >= max_lines.saturating_sub(1) {
                    break;
                }
                items.push(ListItem::new(Line::from(Span::styled(
                    truncate(choice, max_w),
                    Style::default().fg(theme::YELLOW),
                ))));
            }
        }
    }

    items.truncate(max_lines);
    frame.render_widget(List::new(items), inner);
}

fn truncate(text: &str, max_chars: usize) -> String {
    if max_chars <= 3 {
        return ".".repeat(max_chars.min(3));
    }
    let count = text.chars().count();
    if count <= max_chars {
        text.to_string()
    } else {
        let t: String = text.chars().take(max_chars - 3).collect();
        format!("{}...", t)
    }
}
