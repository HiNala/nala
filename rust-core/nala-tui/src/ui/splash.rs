//! Welcome screen — rendered as a bordered card when no messages are present.
//!
//! Inspired by Claude Code / Gemini CLI welcome experience:
//! a clear, professional card showing identity, tips, and shortcuts.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Padding, Paragraph},
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
    let version = env!("CARGO_PKG_VERSION");
    let branch = detect_git_branch(&app.project_root);

    let border_style = Style::default().fg(theme::CYAN);

    let card = Block::default()
        .borders(Borders::ALL)
        .border_style(border_style)
        .title(Span::styled(
            format!(" HiNala v{} ", version),
            Style::default()
                .fg(theme::CYAN)
                .add_modifier(Modifier::BOLD),
        ))
        .title_alignment(Alignment::Left)
        .padding(Padding::new(1, 1, 0, 0));

    let card_height = 16_u16.min(area.height);
    let card_width = 72_u16.min(area.width);

    let vert = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Length(card_height),
            Constraint::Fill(1),
        ])
        .split(area);

    let horiz = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(1),
            Constraint::Length(card_width),
            Constraint::Fill(1),
        ])
        .split(vert[1]);

    let card_area = horiz[1];
    let inner = card.inner(card_area);
    frame.render_widget(card, card_area);

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(10), Constraint::Fill(1)])
        .split(inner);

    let top_cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Length(34), Constraint::Fill(1)])
        .split(rows[0]);

    render_identity(frame, app, top_cols[0], project_name, branch.as_deref());
    render_right_column(frame, top_cols[1]);

    let path_display = abbreviate_path(&app.project_root);
    let path_line = Line::from(Span::styled(
        format!(" {}", path_display),
        Style::default().fg(theme::DARK_GRAY),
    ));
    frame.render_widget(Paragraph::new(path_line), rows[1]);
}

fn render_identity(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    project_name: &str,
    branch: Option<&str>,
) {
    let logo_colors = [
        theme::CYAN,
        theme::CYAN,
        theme::BLUE,
        theme::BLUE,
        theme::MAGENTA,
    ];

    let mut lines: Vec<Line> = LOGO
        .iter()
        .enumerate()
        .map(|(i, line)| {
            Line::from(Span::styled(
                *line,
                Style::default()
                    .fg(logo_colors[i % logo_colors.len()])
                    .add_modifier(Modifier::BOLD),
            ))
        })
        .collect();

    lines.push(Line::from(""));

    let mut info_spans = vec![Span::styled(
        format!(" {}", project_name),
        Style::default()
            .fg(theme::WHITE)
            .add_modifier(Modifier::BOLD),
    )];
    if let Some(b) = branch {
        info_spans.push(Span::styled(
            format!(" on {}", b),
            Style::default().fg(theme::GREEN),
        ));
    }
    lines.push(Line::from(info_spans));

    if !app.llm_provider.is_empty() {
        let provider_display = format_provider(&app.llm_provider);
        let model_display = if app.llm_model.is_empty() {
            String::new()
        } else {
            format!(" · {}", app.llm_model)
        };
        lines.push(Line::from(vec![
            Span::styled(
                format!(" {}", provider_display),
                Style::default().fg(theme::YELLOW),
            ),
            Span::styled(model_display, Style::default().fg(theme::DARK_GRAY)),
        ]));
    } else {
        lines.push(Line::from(Span::styled(
            " Connecting...",
            Style::default().fg(theme::DARK_GRAY),
        )));
    }

    frame.render_widget(Paragraph::new(lines), area);
}

fn render_right_column(frame: &mut Frame, area: Rect) {
    let mut lines = vec![
        Line::from(Span::styled(
            "Getting started",
            Style::default()
                .fg(theme::GREEN)
                .add_modifier(Modifier::BOLD),
        )),
        tip_line("1", "Ask questions or give instructions"),
        tip_line("2", "/analyze to run code analysis"),
        tip_line("3", "/help for all commands"),
        tip_line("4", "/scope path/ to focus on a dir"),
        Line::from(""),
        Line::from(Span::styled(
            "Keyboard shortcuts",
            Style::default()
                .fg(theme::GREEN)
                .add_modifier(Modifier::BOLD),
        )),
        shortcut_line("^B", "toggle file panel"),
        shortcut_line("^E", "toggle session panel"),
        shortcut_line("Tab", "autocomplete commands"),
        shortcut_line("^C", "quit"),
    ];

    if area.height as usize > lines.len() {
        lines.push(Line::from(""));
    }

    frame.render_widget(Paragraph::new(lines), area);
}

fn tip_line(num: &str, text: &str) -> Line<'static> {
    Line::from(vec![
        Span::styled(
            format!("{}. ", num),
            Style::default().fg(theme::DARK_GRAY),
        ),
        Span::styled(text.to_string(), Style::default().fg(theme::GRAY)),
    ])
}

fn shortcut_line(key: &str, desc: &str) -> Line<'static> {
    Line::from(vec![
        Span::styled(
            format!("{:<5}", key),
            Style::default()
                .fg(theme::CYAN)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(desc.to_string(), Style::default().fg(theme::GRAY)),
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
