//! Session history panel (right side, Ctrl+E to toggle).
//!
//! Lists previous analysis sessions from `.nala/` directory.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::Style,
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, List, ListItem},
    Frame,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let sessions = load_sessions(&app.project_root);
    let title = if sessions.is_empty() {
        " Sessions ".to_string()
    } else {
        format!(" Sessions ({}) ", sessions.len())
    };
    let block = Block::default()
        .title(Span::styled(title, theme::bold_accent()))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme::BORDER_NORMAL))
        .style(theme::base_style());
    let items: Vec<ListItem> = if sessions.is_empty() {
        vec![
            ListItem::new(Line::from(Span::styled(
                " No sessions yet.",
                Style::default().fg(theme::FG_DIM),
            ))),
            ListItem::new(Line::from("")),
            ListItem::new(Line::from(Span::styled(
                " Run /analyze to",
                Style::default().fg(theme::FG_DIM),
            ))),
            ListItem::new(Line::from(Span::styled(
                " create a session.",
                Style::default().fg(theme::FG_DIM),
            ))),
        ]
    } else {
        sessions
            .into_iter()
            .map(|s| {
                ListItem::new(Line::from(vec![
                    Span::styled(" ◆ ", Style::default().fg(theme::ACCENT_SECONDARY)),
                    Span::styled(s, Style::default().fg(theme::FG_SECONDARY)),
                ]))
            })
            .collect()
    };

    frame.render_widget(List::new(items).block(block), area);
}

fn load_sessions(project_root: &std::path::Path) -> Vec<String> {
    let sessions_dir = project_root.join(".nala").join("sessions");
    match std::fs::read_dir(&sessions_dir) {
        Ok(entries) => {
            let mut names: Vec<String> = entries
                .filter_map(|e| e.ok())
                .filter(|e| e.path().is_dir())
                .filter_map(|e| e.file_name().into_string().ok())
                .collect();
            names.sort_by(|a, b| b.cmp(a));
            names.truncate(20);
            names
        }
        Err(_) => Vec::new(),
    }
}
