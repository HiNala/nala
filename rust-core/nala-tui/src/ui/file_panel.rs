//! File tree panel (left side, Ctrl+B to toggle).
//! Terminal-native styling with simple border.
//! Tree is cached and only rebuilt when explicitly invalidated.

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
use std::sync::Mutex;
use std::time::Instant;

const SKIP_DIRS: &[&str] = &[
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".nala", ".mypy_cache", ".ruff_cache", ".pytest_cache",
];

const CACHE_TTL_SECS: u64 = 5;

static TREE_CACHE: Mutex<Option<(PathBuf, Instant, Vec<CachedItem>)>> = Mutex::new(None);

#[derive(Clone)]
struct CachedItem {
    text: String,
    color: ratatui::style::Color,
}

pub fn invalidate_cache() {
    if let Ok(mut guard) = TREE_CACHE.lock() {
        *guard = None;
    }
}

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(" files ", Style::default().fg(theme::CYAN).add_modifier(Modifier::BOLD)))
        .borders(Borders::RIGHT)
        .border_style(Style::default().fg(theme::GRAY));

    let cached = get_or_build_tree(&app.project_root);
    let items: Vec<ListItem> = cached
        .iter()
        .map(|ci| ListItem::new(Line::from(Span::styled(ci.text.clone(), Style::default().fg(ci.color)))))
        .collect();

    let list = List::new(items).block(block);
    frame.render_widget(list, area);
}

fn get_or_build_tree(root: &Path) -> Vec<CachedItem> {
    let mut guard = TREE_CACHE.lock().unwrap_or_else(|e| e.into_inner());

    if let Some((cached_root, built_at, items)) = guard.as_ref() {
        if cached_root == root && built_at.elapsed().as_secs() < CACHE_TTL_SECS {
            return items.clone();
        }
    }

    let items = build_tree_items(root);
    *guard = Some((root.to_path_buf(), Instant::now(), items.clone()));
    items
}

fn build_tree_items(root: &Path) -> Vec<CachedItem> {
    let mut items = Vec::new();
    walk_tree(root, 0, 3, &mut items, 200);
    if items.is_empty() {
        items.push(CachedItem {
            text: " (empty)".to_string(),
            color: theme::GRAY,
        });
    }
    items
}

fn walk_tree(current: &Path, depth: usize, max_depth: usize, items: &mut Vec<CachedItem>, max_items: usize) {
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
            items.push(CachedItem {
                text: format!(" {}{}/", indent, name),
                color: theme::YELLOW,
            });
            walk_tree(&path, depth + 1, max_depth, items, max_items);
        } else {
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            let color = theme::lang_color(ext);
            items.push(CachedItem {
                text: format!(" {}  {}", indent, name),
                color,
            });
        }
    }
}
