//! UI module — all rendering components for the Nala TUI.
//!
//! Each submodule is responsible for rendering one region of the screen.
//! None of them mutate state — they only read from `App` and draw to `Frame`.

pub mod command_bar;
pub mod file_panel;
pub mod layout;
pub mod session_panel;
pub mod splash;
pub mod status_bar;
