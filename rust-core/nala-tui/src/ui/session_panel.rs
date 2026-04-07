//! Session history panel (right side, Ctrl+E to toggle).
//! Terminal-native styling with simple border.
//! Session list is cached with a 5-second TTL to avoid filesystem reads at 30fps.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem},
    Frame,
};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Instant;

const SESSION_CACHE_TTL_SECS: u64 = 5;

static SESSION_CACHE: Mutex<Option<(PathBuf, Instant, Vec<String>)>> = Mutex::new(None);

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(" sessions ", Style::default().fg(theme::CYAN).add_modifier(Modifier::BOLD)))
        .borders(Borders::LEFT)
        .border_style(Style::default().fg(theme::GRAY));

    let sessions = load_sessions(&app.project_root);
    let items: Vec<ListItem> = if sessions.is_empty() {
        vec![
            ListItem::new(Line::from(Span::styled(
                " no sessions yet",
                Style::default().fg(theme::GRAY),
            ))),
            ListItem::new(Line::from(Span::styled(
                " run /analyze",
                Style::default().fg(theme::GRAY),
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
    let mut guard = SESSION_CACHE.lock().unwrap_or_else(|e| e.into_inner());
    if let Some((ref cached_root, ref built_at, ref names)) = *guard {
        if cached_root == project_root && built_at.elapsed().as_secs() < SESSION_CACHE_TTL_SECS {
            return names.clone();
        }
    }
    let sessions_dir = project_root.join(".nala").join("sessions");
    let names = match std::fs::read_dir(&sessions_dir) {
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
    };
    *guard = Some((project_root.to_path_buf(), Instant::now(), names.clone()));
    names
}
