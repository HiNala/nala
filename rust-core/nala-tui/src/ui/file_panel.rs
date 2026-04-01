//! File tree panel (left side, Ctrl+B to toggle).
//!
//! Shows the project directory structure with basic health indicators.
//! In Mission 04 polish, this will be interactive with click-to-open.

use crate::app::App;
use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem},
    Frame, layout::Rect,
};
use std::path::Path;

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(" Files ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)))
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Rgb(40, 40, 80)))
        .style(Style::default().bg(Color::Rgb(10, 10, 18)));

    let items = build_tree_items(&app.project_root);
    let list = List::new(items).block(block);
    frame.render_widget(list, area);
}

fn build_tree_items(root: &Path) -> Vec<ListItem<'static>> {
    let mut items = Vec::new();

    let entries = match std::fs::read_dir(root) {
        Ok(e) => e,
        Err(_) => return items,
    };

    let mut names: Vec<std::path::PathBuf> = entries
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            let name = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
            !name.starts_with('.') || name == ".github"
        })
        .collect();

    names.sort_by(|a, b| {
        let a_dir = a.is_dir();
        let b_dir = b.is_dir();
        b_dir.cmp(&a_dir).then(a.cmp(b))
    });

    for path in names.iter().take(40) {
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("?").to_string();
        let (icon, color) = if path.is_dir() {
            ("▶ ", Color::Yellow)
        } else {
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            (file_icon(ext), file_color(ext))
        };
        items.push(ListItem::new(Line::from(Span::styled(
            format!(" {}{}", icon, name),
            Style::default().fg(color),
        ))));
    }

    items
}

fn file_icon(ext: &str) -> &'static str {
    match ext {
        "rs" => "⚙ ",
        "py" => "🐍",
        "js" | "ts" | "jsx" | "tsx" => "⬡ ",
        "go" => "◈ ",
        "md" => "✎ ",
        "toml" | "yaml" | "yml" => "⚙ ",
        "json" => "{ ",
        _ => "  ",
    }
}

fn file_color(ext: &str) -> Color {
    match ext {
        "rs" => Color::Rgb(250, 160, 90),
        "py" => Color::Rgb(70, 170, 230),
        "js" | "jsx" => Color::Rgb(240, 220, 80),
        "ts" | "tsx" => Color::Rgb(50, 140, 220),
        "go" => Color::Rgb(0, 200, 210),
        "md" => Color::Rgb(160, 160, 200),
        _ => Color::White,
    }
}
