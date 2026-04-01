//! LSP client manager.
//!
//! Manages lifecycle of LSP server processes and provides async methods
//! for common operations (go-to-definition, find-references, hover).
//!
//! Mission 05 will implement the full JSON-RPC over stdio transport.
//! This stub provides the correct interface so nala-tui and nala-cli
//! can call it without changes when the implementation lands.

use crate::config::{detect_server, LspServer};
use anyhow::Result;
use std::path::{Path, PathBuf};

/// Result of a go-to-definition query.
#[derive(Debug, Clone)]
pub struct DefinitionLocation {
    pub file_path: PathBuf,
    pub start_line: usize,
    pub start_col: usize,
}

/// A reference found by find-references.
#[derive(Debug, Clone)]
pub struct Reference {
    pub file_path: PathBuf,
    pub line: usize,
    pub col: usize,
}

/// Hover information for a symbol.
#[derive(Debug, Clone)]
pub struct HoverInfo {
    pub contents: String,
}

/// Manages one or more LSP server connections for a project.
pub struct LspManager {
    project_root: PathBuf,
    server: LspServer,
    /// True once the LSP server has been initialised.
    initialized: bool,
}

impl LspManager {
    /// Create a new manager for the given project root.
    ///
    /// Auto-detects the appropriate language server.
    pub fn new(project_root: &Path) -> Self {
        let server = detect_server(project_root);
        tracing::debug!("LSP server detected: {}", server);
        Self {
            project_root: project_root.to_path_buf(),
            server,
            initialized: false,
        }
    }

    /// Return the detected language server type.
    pub fn server(&self) -> &LspServer {
        &self.server
    }

    /// Start the LSP server process and send the initialize request.
    ///
    /// TODO (Mission 05): implement JSON-RPC over stdio transport.
    pub async fn initialize(&mut self) -> Result<()> {
        if self.server == LspServer::None {
            tracing::debug!("No LSP server available for this project");
            return Ok(());
        }
        tracing::info!("Initializing LSP server: {}", self.server);
        // Placeholder — real implementation in Mission 05
        self.initialized = true;
        Ok(())
    }

    /// Find the definition of the symbol at the given file/line/col.
    ///
    /// TODO (Mission 05): implement textDocument/definition RPC.
    pub async fn go_to_definition(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Option<DefinitionLocation>> {
        tracing::debug!("go_to_definition {}:{}:{}", file.display(), line, col);
        Ok(None) // Placeholder
    }

    /// Find all references to the symbol at the given file/line/col.
    ///
    /// TODO (Mission 05): implement textDocument/references RPC.
    pub async fn find_references(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Vec<Reference>> {
        tracing::debug!("find_references {}:{}:{}", file.display(), line, col);
        Ok(vec![]) // Placeholder
    }

    /// Get hover documentation for the symbol at the given file/line/col.
    ///
    /// TODO (Mission 05): implement textDocument/hover RPC.
    pub async fn hover(
        &self,
        file: &Path,
        line: usize,
        col: usize,
    ) -> Result<Option<HoverInfo>> {
        tracing::debug!("hover {}:{}:{}", file.display(), line, col);
        Ok(None) // Placeholder
    }

    /// Shut down the LSP server gracefully.
    pub async fn shutdown(&self) -> Result<()> {
        if self.initialized {
            tracing::info!("Shutting down LSP server: {}", self.server);
        }
        Ok(())
    }
}
