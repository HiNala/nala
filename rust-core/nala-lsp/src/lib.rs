//! nala-lsp: Language Server Protocol client.
//!
//! Provides go-to-definition, find-references, hover information, and
//! diagnostics by connecting to language-specific LSP servers over stdio.
//!
//! Supports: rust-analyzer, pyright, typescript-language-server, gopls.
//! Degrades gracefully when no server is installed.

pub mod client;
pub mod config;
pub(crate) mod transport;

pub use client::{DefinitionLocation, HoverInfo, LspManager, Reference};
