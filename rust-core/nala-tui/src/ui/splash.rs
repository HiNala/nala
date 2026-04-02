//! ASCII art logo and welcome header.
//!
//! Displayed inline as the first content when the app boots.
//! No fullscreen takeover -- the logo is part of the normal message flow.

use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};

pub const LOGO: &[&str] = &[
    r"  _   _ _ _  _       _",
    r" | | | (_) \| | __ _| | __ _",
    r" | |_| | |  \ |/ _` | |/ _` |",
    r" |  _  | | |\  | (_| | | (_| |",
    r" |_| |_|_|_| \_|\__,_|_|\__,_|",
];

pub fn logo_lines() -> Vec<Line<'static>> {
    let colors = [Color::Cyan, Color::Cyan, Color::Blue, Color::Blue, Color::Magenta];
    LOGO.iter()
        .enumerate()
        .map(|(i, line)| {
            Line::from(Span::styled(
                *line,
                Style::default()
                    .fg(colors[i % colors.len()])
                    .add_modifier(Modifier::BOLD),
            ))
        })
        .collect()
}

pub fn welcome_lines(project_name: &str, version: &str, git_branch: Option<&str>) -> Vec<Line<'static>> {
    let mut lines = logo_lines();
    lines.push(Line::from(""));

    let mut info_spans = vec![
        Span::styled(
            format!("  {} ", project_name),
            Style::default().fg(Color::White).add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!("v{}", version),
            Style::default().fg(Color::DarkGray),
        ),
    ];
    if let Some(branch) = git_branch {
        info_spans.push(Span::styled(
            format!("  on {}", branch),
            Style::default().fg(Color::Green),
        ));
    }
    lines.push(Line::from(info_spans));
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "  Tips: type a question, /help for commands, /analyze to audit code",
        Style::default().fg(Color::DarkGray),
    )));
    lines.push(Line::from(Span::styled(
        "  Keys: ^B files  ^E sessions  ^C quit",
        Style::default().fg(Color::DarkGray),
    )));

    lines
}
