//! Keyboard shortcut help overlay.
//!
//! Shown when the user presses `?` (from an empty input field).
//! Any keypress dismisses it.

use crate::ui::theme;
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Paragraph},
    Frame,
};

const SHORTCUTS: &[(&str, &str, &str)] = &[
    // (category, key, description)
    ("Navigation", "Ctrl+B", "Toggle file panel"),
    ("Navigation", "Ctrl+E", "Toggle session panel"),
    ("Navigation", "Ctrl+G", "Toggle agent panel"),
    ("Navigation", "Page Up/Down", "Scroll output"),
    ("Navigation", "Ctrl+U / Ctrl+D", "Half-page scroll"),
    ("Navigation", "Shift+Up/Down", "Always scroll"),
    ("Navigation", "Mouse wheel", "Scroll output"),
    ("Navigation", "Esc", "Snap to bottom / cancel"),
    ("Navigation", "Ctrl+Home / Ctrl+End", "Jump top / bottom"),
    ("Commands", "/review", "Run code review"),
    ("Commands", "/review --diff", "Review uncommitted changes"),
    ("Commands", "/review --copy", "Copy review prompts"),
    ("Commands", "/agent <id>", "View/manage a sub-agent"),
    ("Commands", "/analyze", "Run analysis perspectives"),
    ("Commands", "/investigate", "Deep-dive a problem"),
    ("Commands", "/models", "List available models"),
    ("Commands", "/settings", "View/edit configuration"),
    ("Commands", "/session", "Manage sessions"),
    ("Session", "Enter", "Submit message"),
    ("Session", "Up/Down", "Command history (at bottom)"),
    ("Session", "Tab", "Autocomplete command"),
    ("Session", "Ctrl+C", "Quit"),
    ("Session", "?", "Toggle this help overlay"),
];

pub fn render(frame: &mut Frame, area: Rect) {
    // Center the overlay — max 70 wide, auto height
    let max_w: u16 = 72;
    let max_h: u16 = (SHORTCUTS.len() as u16) + 10;
    let w = max_w.min(area.width.saturating_sub(4));
    let h = max_h.min(area.height.saturating_sub(2));
    let x = area.x + (area.width.saturating_sub(w)) / 2;
    let y = area.y + (area.height.saturating_sub(h)) / 2;
    let popup = Rect { x, y, width: w, height: h };

    frame.render_widget(Clear, popup);

    let block = Block::default()
        .title(Span::styled(
            " Nala Keyboard Shortcuts — press any key to close ",
            Style::default().fg(theme::ACCENT).add_modifier(Modifier::BOLD),
        ))
        .borders(Borders::ALL)
        .border_style(Style::default().fg(theme::BORDER));

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let mut lines: Vec<Line> = Vec::new();
    let mut last_category = "";
    for (category, key, desc) in SHORTCUTS {
        if *category != last_category {
            if !last_category.is_empty() {
                lines.push(Line::from(""));
            }
            lines.push(Line::from(Span::styled(
                format!("  {}", category),
                Style::default().fg(theme::ACCENT).add_modifier(Modifier::BOLD),
            )));
            last_category = category;
        }
        let key_w = 26usize;
        let key_padded = format!("    {:<width$}", key, width = key_w);
        lines.push(Line::from(vec![
            Span::styled(key_padded, Style::default().fg(theme::WHITE)),
            Span::styled(*desc, Style::default().fg(theme::DIM)),
        ]));
    }

    frame.render_widget(
        Paragraph::new(lines)
            .style(Style::default().fg(theme::FG).bg(theme::BG)),
        inner,
    );
}
