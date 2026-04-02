//! File tree panel (left side, Ctrl+B to toggle).
//!
//! Shows a shallow recursive project tree for fast large-repo orientation.

use crate::app::App;
use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem},
    Frame, layout::Rect,
};
use std::path::{Path, PathBuf};

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
    walk_tree(root, root, 0, 3, &mut items, 220);
    if items.is_empty() {
        items.push(ListItem::new(Line::from(Span::styled(
            " [empty]",
            Style::default().fg(Color::DarkGray),
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
            !name.starts_with('.') || name == ".github"
        })
        .collect();
    paths.sort_by(|a, b| {
        let a_dir = a.is_dir();
        let b_dir = b.is_dir();
        b_dir.cmp(&a_dir).then(a.cmp(b))
    });

    for path in paths {
        if items.len() >= max_items {
            return;
        }
        let rel = path
            .strip_prefix(root)
            .map(|p| p.to_string_lossy().replace('\\', "/"))
            .unwrap_or_else(|_| path.display().to_string());
        let indent = "  ".repeat(depth);
        if path.is_dir() {
            items.push(ListItem::new(Line::from(Span::styled(
                format!(" {}[D] {}", indent, rel),
                Style::default().fg(Color::Yellow),
            ))));
            walk_tree(root, &path, depth + 1, max_depth, items, max_items);
        } else {
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            items.push(ListItem::new(Line::from(Span::styled(
                format!(" {}{} {}", indent, file_icon(ext), rel),
                Style::default().fg(file_color(ext)),
            ))));
        }
    }
}

fn file_icon(ext: &str) -> &'static str {
    match ext {
        "rs" => "[R]",
        "py" => "[P]",
        "js" | "ts" | "jsx" | "tsx" => "[J]",
        "go" => "[G]",
        "md" => "[M]",
        "toml" | "yaml" | "yml" => "[C]",
        "json" => "[{]",
        _ => "[F]",
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
