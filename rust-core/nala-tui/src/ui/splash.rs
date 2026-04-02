//! Welcome screen — clean vertical layout when no conversation exists.
//!
//! Renders a compact, readable welcome that works at any terminal width.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Paragraph, Wrap},
    Frame,
};

const LOGO: &[&str] = &[
    r"  _   _ _ _  _       _       ",
    r" | | | (_) \| | __ _| | __ _ ",
    r" | |_| | |  \ |/ _` | |/ _` |",
    r" |  _  | | |\  | (_| | | (_| |",
    r" |_| |_|_|_| \_|\__,_|_|\__,_|",
];

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let project_name = app
        .project_root
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("project");
    let branch = detect_git_branch(&app.project_root);
    let path_display = abbreviate_path(&app.project_root);

    if area.width < 72 || area.height < 16 {
        render_compact(frame, app, area, project_name, branch.as_deref(), &path_display);
        return;
    }

    let logo_colors = [
        theme::CYAN,
        theme::CYAN,
        theme::BLUE,
        theme::BLUE,
        theme::MAGENTA,
    ];

    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(""));

    for (i, logo_line) in LOGO.iter().enumerate() {
        lines.push(Line::from(Span::styled(
            format!("  {}", logo_line),
            Style::default()
                .fg(logo_colors[i % logo_colors.len()])
                .add_modifier(Modifier::BOLD),
        )));
    }

    lines.push(Line::from(""));

    let mut info_spans = vec![Span::styled(
        format!("  {}", project_name),
        Style::default()
            .fg(theme::WHITE)
            .add_modifier(Modifier::BOLD),
    )];
    if let Some(b) = branch.as_deref() {
        info_spans.push(Span::styled(
            format!(" on {}", b),
            Style::default().fg(theme::GREEN),
        ));
    }
    lines.push(Line::from(info_spans));

    if !app.llm_provider.is_empty() {
        let provider_display = format_provider(&app.llm_provider);
        let model_part = if app.llm_model.is_empty() {
            String::new()
        } else {
            format!(" / {}", app.llm_model)
        };
        lines.push(Line::from(Span::styled(
            format!("  {}{}", provider_display, model_part),
            Style::default().fg(theme::YELLOW),
        )));
    } else {
        lines.push(Line::from(Span::styled(
            "  Connecting...",
            Style::default().fg(theme::GRAY),
        )));
    }

    lines.push(Line::from(Span::styled(
        format!("  {}", path_display),
        Style::default().fg(theme::GRAY),
    )));

    if app.stats.total_files > 0 || app.stats.total_functions > 0 {
        let mut parts: Vec<String> = Vec::new();
        if app.stats.total_files > 0 {
            parts.push(format!("{} files", app.stats.total_files));
        }
        if app.stats.total_functions > 0 {
            parts.push(format!("{} symbols", app.stats.total_functions));
        }
        lines.push(Line::from(Span::styled(
            format!("  Indexed: {}", parts.join(", ")),
            Style::default().fg(theme::MAGENTA),
        )));
    }

    if let Some(intel) = &app.startup_intel {
        if !intel.project_types.is_empty() {
            let types = intel.project_types.join(", ");
            lines.push(Line::from(Span::styled(
                format!("  Project: {}", types),
                Style::default().fg(theme::CYAN),
            )));
        }

        if !intel.git_branch.is_empty() {
            let mut git_line = format!("  git: {}", intel.git_branch);
            if intel.git_uncommitted > 0 {
                git_line.push_str(&format!("  ({} uncommitted)", intel.git_uncommitted));
            }
            if intel.git_ahead > 0 {
                git_line.push_str(&format!("  {} ahead", intel.git_ahead));
            }
            if intel.git_behind > 0 {
                git_line.push_str(&format!("  {} behind", intel.git_behind));
            }
            lines.push(Line::from(Span::styled(
                git_line,
                Style::default().fg(theme::GREEN),
            )));
        }

        if !intel.entry_points.is_empty() {
            let ep = intel.entry_points.iter().take(3)
                .cloned().collect::<Vec<_>>().join(", ");
            lines.push(Line::from(Span::styled(
                format!("  Entry: {}", ep),
                Style::default().fg(theme::GRAY),
            )));
        }

        if !intel.suggestions.is_empty() {
            lines.push(Line::from(""));
            lines.push(Line::from(Span::styled(
                "  Suggested next steps",
                Style::default()
                    .fg(theme::GREEN)
                    .add_modifier(Modifier::BOLD),
            )));
            for suggestion in &intel.suggestions {
                lines.push(Line::from(Span::styled(
                    format!("  · {}", suggestion),
                    Style::default().fg(theme::WHITE),
                )));
            }
        }
    } else {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            "  Getting started",
            Style::default()
                .fg(theme::GREEN)
                .add_modifier(Modifier::BOLD),
        )));
        lines.push(tip_line("  · ", "Type a question or instruction to chat"));
        lines.push(tip_line("  · ", "/agent <goal> to start an autonomous run"));
        lines.push(tip_line("  · ", "/model to check your LLM connection"));
        lines.push(tip_line("  · ", "/help for all commands"));
    }

    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "  Keys",
        Style::default()
            .fg(theme::GREEN)
            .add_modifier(Modifier::BOLD),
    )));
    lines.push(shortcut_line("  Tab     ", "autocomplete commands"));
    lines.push(shortcut_line("  Ctrl+B  ", "file panel"));
    lines.push(shortcut_line("  Ctrl+G  ", "agent panel"));
    lines.push(shortcut_line("  Ctrl+C  ", "quit"));

    frame.render_widget(Paragraph::new(lines).wrap(Wrap { trim: false }), area);
}

fn render_compact(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    project_name: &str,
    branch: Option<&str>,
    path_display: &str,
) {
    let mut lines = vec![
        Line::from(Span::styled(
            "  HiNala",
            Style::default()
                .fg(theme::CYAN)
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
    ];

    let mut project_spans = vec![Span::styled(
        format!("  {}", project_name),
        Style::default()
            .fg(theme::WHITE)
            .add_modifier(Modifier::BOLD),
    )];
    if let Some(branch) = branch {
        project_spans.push(Span::styled(
            format!(" on {}", branch),
            Style::default().fg(theme::GREEN),
        ));
    }
    lines.push(Line::from(project_spans));

    if !app.llm_provider.is_empty() {
        let provider = format_provider(&app.llm_provider);
        let model = if app.llm_model.is_empty() {
            String::new()
        } else {
            format!(" / {}", app.llm_model)
        };
        lines.push(Line::from(Span::styled(
            format!("  {}{}", provider, model),
            Style::default().fg(theme::YELLOW),
        )));
    } else {
        lines.push(Line::from(Span::styled(
            "  Connecting...",
            Style::default().fg(theme::GRAY),
        )));
    }

    lines.push(Line::from(Span::styled(
        format!("  {}", path_display),
        Style::default().fg(theme::GRAY),
    )));
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "  Type a question or /help for commands",
        Style::default().fg(theme::WHITE),
    )));
    lines.push(Line::from(Span::styled(
        "  Tab autocomplete  Ctrl+B files  Ctrl+G agent",
        Style::default().fg(theme::GRAY),
    )));

    frame.render_widget(Paragraph::new(lines).wrap(Wrap { trim: false }), area);
}

fn tip_line(prefix: &str, text: &str) -> Line<'static> {
    Line::from(vec![
        Span::styled(prefix.to_string(), Style::default().fg(theme::GRAY)),
        Span::styled(text.to_string(), Style::default().fg(theme::WHITE)),
    ])
}

fn shortcut_line(key: &str, desc: &str) -> Line<'static> {
    Line::from(vec![
        Span::styled(
            key.to_string(),
            Style::default()
                .fg(theme::CYAN)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(desc.to_string(), Style::default().fg(theme::WHITE)),
    ])
}

fn format_provider(s: &str) -> String {
    match s {
        "openai" => "OpenAI".to_string(),
        "anthropic" => "Anthropic".to_string(),
        "google" => "Google".to_string(),
        "ollama" => "Ollama".to_string(),
        other => {
            let mut c = other.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
            }
        }
    }
}

fn abbreviate_path(path: &std::path::Path) -> String {
    let s = path.to_string_lossy();
    let s = s.strip_prefix(r"\\?\").unwrap_or(&s);
    if let Ok(home) = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")) {
        if let Ok(rel) = path.strip_prefix(&home) {
            return format!("~/{}", rel.to_string_lossy().replace('\\', "/"));
        }
    }
    s.to_string()
}

fn detect_git_branch(root: &std::path::Path) -> Option<String> {
    let head = root.join(".git").join("HEAD");
    let contents = std::fs::read_to_string(head).ok()?;
    let trimmed = contents.trim();
    if let Some(rest) = trimmed.strip_prefix("ref: refs/heads/") {
        Some(rest.to_string())
    } else {
        Some(trimmed[..8.min(trimmed.len())].to_string())
    }
}
