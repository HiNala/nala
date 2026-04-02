//! Session history panel (right side, Ctrl+E to toggle).
//! Terminal-native styling with simple border.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem},
    Frame,
};

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(" sessions ", Style::default().fg(theme::CYAN).add_modifier(Modifier::BOLD)))
        .borders(Borders::LEFT)
        .border_style(Style::default().fg(theme::DARK_GRAY));

    let sessions = load_sessions(&app.project_root);
    let items: Vec<ListItem> = if sessions.is_empty() {
        vec![
            ListItem::new(Line::from(Span::styled(
                " no sessions yet",
                Style::default().fg(theme::DARK_GRAY),
            ))),
            ListItem::new(Line::from(Span::styled(
                " run /analyze",
                Style::default().fg(theme::DARK_GRAY),
            ))),
        ]
    } else {
        sessions
            .into_iter()
            .map(|s| {
                ListItem::new(Line::from(Span::styled(
                    format!(" {}", s),
                    Style::default().fg(theme::GRAY),
                )))
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
