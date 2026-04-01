# Mission 05: LSP Client Integration

## Objective

Build the Language Server Protocol client that connects Nala to external language servers (rust-analyzer, pyright, gopls, typescript-language-server, etc.) to provide real-time code intelligence: go-to-definition, find-references, hover information, and diagnostics. This is how OpenCode and Claude Code achieve 900x faster code navigation compared to grep-based search.

## Why This Matters

Tree-sitter gives us syntax-level understanding (the shape of the code). LSP gives us semantic understanding (what the code means). With LSP, Nala can answer questions like "where is this function defined?", "what calls this function?", and "what type does this variable have?" in 50ms instead of 45 seconds. This makes the difference between a tool that feels intelligent and one that feels like a glorified text search.

OpenCode's LSP integration is one of its strongest features. It automatically detects and starts language servers, synchronizes file changes, and feeds diagnostics to the AI agent. Nala replicates this pattern.

## Implementation Steps

### Step 1: LSP server configuration (config.rs)

Create an `LspConfig` struct that maps languages to their LSP server commands. Support auto-detection by checking if the server binary exists in PATH.

Default configurations for:
- Rust: `rust-analyzer` (no args needed)
- Python: `pyright-langserver --stdio` or `pylsp`
- TypeScript/JavaScript: `typescript-language-server --stdio`
- Go: `gopls serve`

Store configs in a `.nala/lsp.toml` file so users can customize.

### Step 2: LSP client lifecycle (client.rs)

Create an `LspClient` struct that manages a single LSP server process:
- Spawn the server process with stdin/stdout pipes
- Send the `initialize` request with workspace root and capabilities
- Handle the `initialized` notification
- Send `textDocument/didOpen` when a file is first accessed
- Send `textDocument/didChange` when a file is modified
- Send `textDocument/didClose` when done with a file
- Handle `textDocument/publishDiagnostics` notifications (cache them)
- Implement clean shutdown

Use tokio for async I/O. The LSP protocol uses JSON-RPC over stdin/stdout, with Content-Length headers separating messages.

### Step 3: LSP request methods (client.rs continued)

Implement these LSP request methods on LspClient:
- `goto_definition(file: &str, line: u32, col: u32) -> Result<Vec<Location>>`: textDocument/definition
- `find_references(file: &str, line: u32, col: u32) -> Result<Vec<Location>>`: textDocument/references
- `hover(file: &str, line: u32, col: u32) -> Result<Option<HoverInfo>>`: textDocument/hover
- `document_symbols(file: &str) -> Result<Vec<DocumentSymbol>>`: textDocument/documentSymbol
- `get_diagnostics(file: &str) -> Result<Vec<Diagnostic>>`: Return cached diagnostics

### Step 4: LSP manager (lib.rs)

Create an `LspManager` that manages multiple LspClient instances (one per language). It:
- Detects which languages are present in the project (from the scanner results)
- Starts LSP servers for detected languages (in background)
- Routes requests to the correct client based on file extension
- Handles server crashes gracefully (log error, attempt restart once)
- Provides a unified API that the TUI and Python bridge can call

### Step 5: File synchronization

Implement a file watcher pattern (using notify crate or polling) that detects file changes and sends `didChange` notifications to the appropriate LSP server. Use debouncing (300ms) to avoid flooding the server during rapid edits or git operations.

### Step 6: Wire into the TUI

Add keyboard shortcut `gd` (go-to-definition, vim-style) when a symbol is selected. Add `gr` (go-to-references). Show hover info in a popup when the user pauses on a symbol. Display diagnostics (errors, warnings) in the status bar and as inline annotations.

### Step 7: Write tests

- Test JSON-RPC message serialization/deserialization
- Test the initialize handshake sequence
- Integration test with a real rust-analyzer instance on a small Rust project (if available in CI)

## Acceptance Criteria

- LSP servers start automatically for detected languages
- Go-to-definition returns results in under 100ms
- Find-references returns results in under 200ms
- Diagnostics are cached and accessible without blocking
- Server crashes are handled gracefully without crashing Nala
- No source file exceeds 400 lines

## Key Dependencies

- lsp-types (LSP protocol types)
- tokio (async I/O for server communication)
- serde_json (JSON-RPC serialization)
- notify (file watching, optional)

## Estimated Complexity

High. The LSP protocol has many moving parts. The JSON-RPC framing with Content-Length headers requires precise byte-level parsing. Handling server lifecycle (start, crash, restart) adds complexity.
