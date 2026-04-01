//! LSP server configuration and auto-detection.
//!
//! Detects the appropriate language server for a project by inspecting
//! the project root for known config files and Cargo.toml / pyproject.toml.

use std::path::Path;

/// A supported language server.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LspServer {
    /// rust-analyzer for Rust projects.
    RustAnalyzer,
    /// pyright for Python projects.
    Pyright,
    /// typescript-language-server for JS/TS projects.
    TypeScriptLanguageServer,
    /// gopls for Go projects.
    Gopls,
    /// No server detected.
    None,
}

impl LspServer {
    /// The command to launch this server.
    pub fn command(&self) -> Option<&'static str> {
        match self {
            Self::RustAnalyzer => Some("rust-analyzer"),
            Self::Pyright => Some("pyright-langserver --stdio"),
            Self::TypeScriptLanguageServer => Some("typescript-language-server --stdio"),
            Self::Gopls => Some("gopls"),
            Self::None => None,
        }
    }
}

impl std::fmt::Display for LspServer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::RustAnalyzer => write!(f, "rust-analyzer"),
            Self::Pyright => write!(f, "pyright"),
            Self::TypeScriptLanguageServer => write!(f, "typescript-language-server"),
            Self::Gopls => write!(f, "gopls"),
            Self::None => write!(f, "none"),
        }
    }
}

/// Detect the primary language server for a project root.
///
/// Inspects config files to determine the project type and returns
/// the most appropriate LSP server. Projects with multiple languages
/// may need multiple servers — that is handled in Mission 05.
pub fn detect_server(root: &Path) -> LspServer {
    if root.join("Cargo.toml").exists() {
        return LspServer::RustAnalyzer;
    }
    if root.join("pyproject.toml").exists() || root.join("setup.py").exists() {
        return LspServer::Pyright;
    }
    if root.join("package.json").exists() {
        return LspServer::TypeScriptLanguageServer;
    }
    if root.join("go.mod").exists() {
        return LspServer::Gopls;
    }
    LspServer::None
}
