//! File tree panel (left side, Ctrl+B to toggle).
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
use std::path::{Path, PathBuf};

const SKIP_DIRS: &[&str] = &[
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".nala", ".mypy_cache", ".ruff_cache", ".pytest_cache",
];

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(" files ", Style::default().fg(theme::CYAN).add_modifier(Modifier::BOLD)))
        .borders(Borders::RIGHT)
        .border_style(Style::default().fg(theme::DARK_GRAY));

    let items = build_tree_items(&app.project_root);
    let list = List::new(items).block(block);
    frame.render_widget(list, area);
}

fn build_tree_items(root: &Path) -> Vec<ListItem<'static>> {
    let mut items = Vec::new();
    walk_tree(root, 0, 3, &mut items, 200);
    if items.is_empty() {
        items.push(ListItem::new(Line::from(Span::styled(
            " (empty)",
            Style::default().fg(theme::DARK_GRAY),
        ))));
    }
    items
}

fn walk_tree(current: &Path, depth: usize, max_depth: usize, items: &mut Vec<ListItem<'static>>, max_items: usize) {
    if depth > max_depth || items.len() >= max_items {
        return;
    }
    let entries = match std::fs::read_dir(current) {
        Ok(e) => e,
        Err(_) => return,
    };
    let mut paths: Vec<PathBuf> = entries
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            let name = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
            !SKIP_DIRS.contains(&name) && (!name.starts_with('.') || name == ".github")
        })
        .collect();
    paths.sort_by(|a, b| b.is_dir().cmp(&a.is_dir()).then(a.cmp(b)));

    let indent = "  ".repeat(depth);

    for path in paths {
        if items.len() >= max_items {
            return;
        }
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("?").to_string();

        if path.is_dir() {
            items.push(ListItem::new(Line::from(Span::styled(
                format!(" {}{}/", indent, name),
                Style::default().fg(theme::YELLOW),
            ))));
            walk_tree(&path, depth + 1, max_depth, items, max_items);
        } else {
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            let color = theme::lang_color(ext);
            items.push(ListItem::new(Line::from(Span::styled(
                format!(" {}  {}", indent, name),
                Style::default().fg(color),
            ))));
        }
    }
}
