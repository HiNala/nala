//! Terminal-native color theme for HiNala.
//!
//! Uses a Tokyo Night-inspired palette while still rendering cleanly in
//! terminals that only partially support styling.

use ratatui::style::{Color, Modifier, Style};

pub const BG: Color = Color::Rgb(0x1a, 0x1b, 0x26);
pub const FG: Color = Color::Rgb(0xc0, 0xca, 0xf5);
pub const ACCENT: Color = Color::Rgb(0x7a, 0xa2, 0xf7);
pub const SUCCESS: Color = Color::Rgb(0x9e, 0xce, 0x6a);
pub const WARNING: Color = Color::Rgb(0xe0, 0xaf, 0x68);
pub const ERROR: Color = Color::Rgb(0xf7, 0x76, 0x8e);
pub const INFO: Color = Color::Rgb(0x7d, 0xcf, 0xff);
pub const DIM: Color = Color::Rgb(0x56, 0x5f, 0x89);
pub const BORDER: Color = Color::Rgb(0x3b, 0x42, 0x61);
pub const SELECTION_BG: Color = Color::Rgb(0x28, 0x34, 0x57);
pub const USER_INPUT_BG: Color = Color::Rgb(0x24, 0x28, 0x3b);

pub const CYAN: Color = INFO;
pub const GREEN: Color = SUCCESS;
pub const YELLOW: Color = WARNING;
pub const RED: Color = ERROR;
pub const MAGENTA: Color = Color::Rgb(0xbb, 0x9a, 0xf7);
pub const BLUE: Color = ACCENT;
pub const WHITE: Color = FG;
pub const GRAY: Color = DIM;
pub const DARK_GRAY: Color = BORDER;

pub const LANG_RUST: Color = YELLOW;
pub const LANG_PYTHON: Color = BLUE;
pub const LANG_JS: Color = YELLOW;
pub const LANG_TS: Color = CYAN;
pub const LANG_GO: Color = CYAN;
pub const LANG_MD: Color = GRAY;

pub const DIFF_ADD: Color = GREEN;
pub const DIFF_REMOVE: Color = RED;

pub fn base() -> Style {
    Style::default().fg(FG).bg(BG)
}

pub fn dim() -> Style {
    Style::default().fg(DIM)
}

pub fn muted() -> Style {
    Style::default().fg(DIM)
}

pub fn bold_accent() -> Style {
    Style::default().fg(ACCENT).add_modifier(Modifier::BOLD)
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
