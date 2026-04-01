//! Session history panel (right side, Ctrl+E to toggle).
//!
//! Lists previous analysis sessions from `.nala/` directory.
//! In Mission 10, this will show full session details and allow resuming.

use crate::app::App;
use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem},
    Frame, layout::Rect,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(
            " Sessions ",
            Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
        ))
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Rgb(40, 40, 80)))
        .style(Style::default().bg(Color::Rgb(10, 10, 18)));

    let sessions = load_sessions(&app.project_root);
    let items: Vec<ListItem> = if sessions.is_empty() {
        vec![ListItem::new(Line::from(Span::styled(
            " No sessions yet.",
            Style::default().fg(Color::DarkGray),
        )))]
    } else {
        sessions
            .into_iter()
            .map(|s| {
                ListItem::new(Line::from(Span::styled(
                    format!(" {}", s),
                    Style::default().fg(Color::White),
                )))
            })
            .collect()
    };

    frame.render_widget(List::new(items).block(block), area);
}

/// Load session directory names from `.nala/sessions/`.
fn load_sessions(project_root: &std::path::Path) -> Vec<String> {
    let sessions_dir = project_root.join(".nala").join("sessions");
    match std::fs::read_dir(&sessions_dir) {
        Ok(entries) => {
            let mut names: Vec<String> = entries
                .filter_map(|e| e.ok())
                .filter(|e| e.path().is_dir())
                .filter_map(|e| {
                    e.file_name().into_string().ok()
                })
                .collect();
            names.sort_by(|a, b| b.cmp(a)); // newest first
            names.truncate(20);
            names
        }
        Err(_) => Vec::new(),
    }
}
