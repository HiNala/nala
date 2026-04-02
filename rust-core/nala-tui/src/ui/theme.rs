//! Centralized color theme for the Nala TUI.
//!
//! Every color used in the interface is defined here as a semantic constant.
//! This makes the palette easy to adjust and ensures visual consistency
//! across all panels, bars, and overlays.

use ratatui::style::{Color, Modifier, Style};

// ── Base palette ────────────────────────────────────────────────────────────

pub const BG_DEEP: Color = Color::Rgb(8, 8, 16);
pub const BG_BASE: Color = Color::Rgb(12, 12, 22);
pub const BG_SURFACE: Color = Color::Rgb(18, 18, 30);
pub const BG_ELEVATED: Color = Color::Rgb(24, 24, 40);
pub const BG_OVERLAY: Color = Color::Rgb(30, 30, 50);

pub const FG_PRIMARY: Color = Color::Rgb(220, 220, 235);
pub const FG_SECONDARY: Color = Color::Rgb(140, 140, 170);
pub const FG_MUTED: Color = Color::Rgb(80, 80, 110);
pub const FG_DIM: Color = Color::Rgb(55, 55, 75);

// ── Accent colors ───────────────────────────────────────────────────────────

pub const ACCENT_PRIMARY: Color = Color::Rgb(100, 200, 255);
pub const ACCENT_SECONDARY: Color = Color::Rgb(160, 140, 255);
pub const ACCENT_WARM: Color = Color::Rgb(255, 180, 100);
pub const ACCENT_GREEN: Color = Color::Rgb(80, 220, 140);
pub const ACCENT_ROSE: Color = Color::Rgb(255, 110, 140);

// ── Semantic colors ─────────────────────────────────────────────────────────

pub const SUCCESS: Color = ACCENT_GREEN;
pub const WARNING: Color = Color::Rgb(255, 200, 60);
pub const ERROR: Color = Color::Rgb(255, 90, 90);
pub const INFO: Color = ACCENT_PRIMARY;

// ── Border & separator ──────────────────────────────────────────────────────

pub const BORDER_NORMAL: Color = Color::Rgb(40, 40, 65);
pub const BORDER_FOCUSED: Color = ACCENT_PRIMARY;
pub const BORDER_DIM: Color = Color::Rgb(28, 28, 45);

// ── Language file colors ────────────────────────────────────────────────────

pub const LANG_RUST: Color = Color::Rgb(250, 160, 90);
pub const LANG_PYTHON: Color = Color::Rgb(70, 170, 230);
pub const LANG_JS: Color = Color::Rgb(240, 220, 80);
pub const LANG_TS: Color = Color::Rgb(50, 140, 220);
pub const LANG_GO: Color = Color::Rgb(0, 200, 210);
pub const LANG_MARKDOWN: Color = Color::Rgb(160, 160, 200);
pub const LANG_DEFAULT: Color = FG_SECONDARY;

// ── Message role colors ─────────────────────────────────────────────────────

pub const MSG_USER: Color = FG_PRIMARY;
pub const MSG_ASSISTANT: Color = ACCENT_PRIMARY;
pub const MSG_SYSTEM: Color = FG_MUTED;
pub const MSG_ERROR: Color = ERROR;

// ── Health indicators ───────────────────────────────────────────────────────

pub const HEALTH_GOOD: Color = ACCENT_GREEN;
pub const HEALTH_WARN: Color = WARNING;
pub const HEALTH_BAD: Color = ERROR;

// ── Diff colors ─────────────────────────────────────────────────────────────

pub const DIFF_ADD: Color = ACCENT_GREEN;
pub const DIFF_REMOVE: Color = ACCENT_ROSE;
pub const DIFF_CONTEXT: Color = FG_SECONDARY;

// ── Progress / gauge ────────────────────────────────────────────────────────

pub const GAUGE_FILLED: Color = ACCENT_PRIMARY;
pub const GAUGE_EMPTY: Color = Color::Rgb(30, 30, 50);

// ── Style helpers ───────────────────────────────────────────────────────────

pub fn base_style() -> Style {
    Style::default().bg(BG_BASE).fg(FG_PRIMARY)
}

pub fn surface_style() -> Style {
    Style::default().bg(BG_SURFACE).fg(FG_PRIMARY)
}

pub fn muted_style() -> Style {
    Style::default().fg(FG_MUTED)
}

pub fn accent_style() -> Style {
    Style::default().fg(ACCENT_PRIMARY)
}

pub fn bold_accent() -> Style {
    Style::default()
        .fg(ACCENT_PRIMARY)
        .add_modifier(Modifier::BOLD)
}

pub fn badge_style(bg: Color, fg: Color) -> Style {
    Style::default().bg(bg).fg(fg).add_modifier(Modifier::BOLD)
}

pub fn border_block(title: &str) -> ratatui::widgets::Block<'_> {
    ratatui::widgets::Block::default()
        .borders(ratatui::widgets::Borders::ALL)
        .border_style(Style::default().fg(BORDER_NORMAL))
        .title(format!(" {} ", title))
        .title_style(bold_accent())
        .style(base_style())
}

pub fn lang_color(ext: &str) -> Color {
    match ext {
        "rs" => LANG_RUST,
        "py" => LANG_PYTHON,
        "js" | "jsx" => LANG_JS,
        "ts" | "tsx" => LANG_TS,
        "go" => LANG_GO,
        "md" => LANG_MARKDOWN,
        _ => LANG_DEFAULT,
    }
}
