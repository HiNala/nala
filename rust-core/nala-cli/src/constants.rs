//! Application-wide constants.
//!
//! All references to the app name go through APP_NAME.
//! To rename the application, change APP_NAME here — that is the only required change.

/// The application name. Change this single value to rename the entire application.
pub const APP_NAME: &str = "HiNala";

/// The application version, pulled from Cargo.toml at compile time.
pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

/// The application description shown in --help output.
pub const APP_DESCRIPTION: &str =
    "Terminal-first AI-powered coding environment. Fast, deep, keyboard-driven.";

