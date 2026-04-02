//! Terminal-native color theme for HiNala.
//!
//! Uses Color::Reset for backgrounds (respects user's terminal theme) and
//! ANSI-compatible colors for accents. No custom RGB backgrounds.

use ratatui::style::{Color, Modifier, Style};

pub const CYAN: Color = Color::Cyan;
pub const GREEN: Color = Color::Green;
pub const YELLOW: Color = Color::Yellow;
pub const RED: Color = Color::Red;
pub const MAGENTA: Color = Color::Magenta;
pub const BLUE: Color = Color::Blue;
pub const WHITE: Color = Color::White;
pub const GRAY: Color = Color::Gray;
pub const DARK_GRAY: Color = Color::DarkGray;

pub const ACCENT: Color = CYAN;
pub const SUCCESS: Color = GREEN;
pub const WARNING: Color = YELLOW;
pub const ERROR: Color = RED;

pub const LANG_RUST: Color = YELLOW;
pub const LANG_PYTHON: Color = BLUE;
pub const LANG_JS: Color = YELLOW;
pub const LANG_TS: Color = CYAN;
pub const LANG_GO: Color = CYAN;
pub const LANG_MD: Color = GRAY;

pub const DIFF_ADD: Color = GREEN;
pub const DIFF_REMOVE: Color = RED;

pub fn base() -> Style {
    Style::reset()
}

pub fn dim() -> Style {
    Style::default().fg(DARK_GRAY)
}

pub fn muted() -> Style {
    Style::default().fg(GRAY)
}

pub fn bold_accent() -> Style {
    Style::default().fg(CYAN).add_modifier(Modifier::BOLD)
}

pub fn lang_color(ext: &str) -> Color {
    match ext {
        "rs" => LANG_RUST,
        "py" => LANG_PYTHON,
        "js" | "jsx" => LANG_JS,
        "ts" | "tsx" => LANG_TS,
        "go" => LANG_GO,
        "md" => LANG_MD,
        _ => GRAY,
    }
}
