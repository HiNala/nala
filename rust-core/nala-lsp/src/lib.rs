//! nala-lsp: Language Server Protocol client.
//!
//! Provides go-to-definition, find-references, hover information, and
//! diagnostics by connecting to language-specific LSP servers.
//!
//! Currently a well-structured stub. Mission 05 will implement the full
//! LSP lifecycle: initialize → textDocument/definition → textDocument/references.

pub mod client;
pub mod config;

pub use client::LspManager;
