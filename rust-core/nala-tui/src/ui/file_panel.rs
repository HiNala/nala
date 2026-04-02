//! File tree panel (left side, Ctrl+B to toggle).
//!
//! Shows a shallow recursive project tree with language-colored icons
//! and directory skip rules aligned with the scanner.

use crate::app::App;
use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, Scrollbar, ScrollbarOrientation, ScrollbarState},
    Frame,
};
use std::path::{Path, PathBuf};

const SKIP_DIRS: &[&str] = &[
    "node_modules",
    "target",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".nala",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
];

pub fn render(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(
            " Files ",
            theme::bold_accent(),
        ))
        .borders(Borders::ALL)
        .border_style(Style::default().fg(theme::BORDER_NORMAL))
        .style(theme::base_style());

    let items = build_tree_items(&app.project_root);
    let total = items.len();
    let list = List::new(items).block(block);
    frame.render_widget(list, area);

    if total > area.height.saturating_sub(2) as usize {
        let mut scrollbar_state = ScrollbarState::new(total);
        frame.render_stateful_widget(
            Scrollbar::new(ScrollbarOrientation::VerticalRight)
                .thumb_style(Style::default().fg(theme::FG_DIM))
                .track_style(Style::default().fg(theme::BORDER_DIM)),
            area,
            &mut scrollbar_state,
        );
    }
}

fn build_tree_items(root: &Path) -> Vec<ListItem<'static>> {
    let mut items = Vec::new();
    walk_tree(root, root, 0, 3, &mut items, 300);
    if items.is_empty() {
        items.push(ListItem::new(Line::from(Span::styled(
            " (empty project)",
            Style::default().fg(theme::FG_DIM),
        ))));
    }
    items
}

fn walk_tree(
    root: &Path,
    current: &Path,
    depth: usize,
    max_depth: usize,
    items: &mut Vec<ListItem<'static>>,
    max_items: usize,
) {
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
            if SKIP_DIRS.contains(&name) {
                return false;
            }
            if name.starts_with('.') && name != ".github" {
                return false;
            }
            true
        })
        .collect();
    paths.sort_by(|a, b| {
        let a_dir = a.is_dir();
        let b_dir = b.is_dir();
        b_dir.cmp(&a_dir).then(a.cmp(b))
    });

    let indent = "  ".repeat(depth);
    let connector = if depth == 0 { "" } else { "├ " };

    for path in paths {
        if items.len() >= max_items {
            return;
        }
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("?")
            .to_string();

        if path.is_dir() {
            items.push(ListItem::new(Line::from(vec![
                Span::styled(
                    format!(" {}{}", indent, connector),
                    Style::default().fg(theme::FG_DIM),
                ),
                Span::styled(
                    format!("{}/", name),
                    Style::default()
                        .fg(theme::ACCENT_WARM)
                        .add_modifier(Modifier::BOLD),
                ),
            ])));
            walk_tree(root, &path, depth + 1, max_depth, items, max_items);
        } else {
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            let icon = file_icon(ext);
            let color = theme::lang_color(ext);
            items.push(ListItem::new(Line::from(vec![
                Span::styled(
                    format!(" {}{}", indent, connector),
                    Style::default().fg(theme::FG_DIM),
                ),
                Span::styled(format!("{} ", icon), Style::default().fg(color)),
                Span::styled(name, Style::default().fg(theme::FG_SECONDARY)),
            ])));
        }
    }
}

fn file_icon(ext: &str) -> &'static str {
    match ext {
        "rs" => "●",
        "py" => "◆",
        "js" | "jsx" => "▲",
        "ts" | "tsx" => "▲",
        "go" => "◇",
        "md" => "▪",
        "toml" | "yaml" | "yml" | "json" => "◈",
        _ => "○",
    }
}
