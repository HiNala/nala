# Mission 05: LSP Client Integration

## Objective

Connect Nala to Language Server Protocol servers (rust-analyzer, pyright, gopls, typescript-language-server) to enable go-to-definition, find-references, hover information, and real-time diagnostics.

## Why This Matters

LSP integration transforms Nala from a file browser + AI chat into a genuine code navigation tool. Go-to-definition at < 100ms. Find all usages of a function across the entire codebase. See type information by hovering over a symbol. This is how Claude Code and OpenCode achieve code intelligence, and it's what distinguishes a tool from a toy.

## Context

The `nala-lsp` crate already has the structure stub. This mission implements the actual JSON-RPC communication layer using stdio transport (the standard LSP protocol).

## Implementation Steps

### Step 1: Add JSON-RPC transport

Add to nala-lsp/Cargo.toml:
```toml
tokio-util = { version = "0.7", features = ["codec"] }
bytes = "1"
```

Create `nala-lsp/src/transport.rs`:
- Start a child process for the LSP server (`rust-analyzer`, etc.)
- Establish stdin/stdout pipes
- Implement `Content-Length: N\r\n\r\n{json}` framing per the LSP spec
- Create async `send(request)` and `recv() -> response` methods

### Step 2: Implement the initialize handshake

In `client.rs`, implement `initialize()`:
1. Send `initialize` request with workspace root and capabilities
2. Wait for `InitializeResult`
3. Send `initialized` notification
4. Mark `self.initialized = true`

### Step 3: Implement textDocument/definition

```rust
pub async fn go_to_definition(
    &self, file: &Path, line: usize, col: usize
) -> Result<Option<DefinitionLocation>>
```

Convert to LSP `TextDocumentPositionParams`, send request, parse `Location` response.

### Step 4: Implement textDocument/references

Same pattern as go-to-definition but returns `Vec<Location>`.

### Step 5: Implement textDocument/hover

Returns markdown documentation for the symbol at the given position.

### Step 6: Wire LSP into the TUI

In `nala-tui/src/app.rs`, when the user presses `F12` (go-to-definition) or types `/def symbol`, dispatch to the LSP manager and show results in the main content area.

## Acceptance Criteria

- [ ] rust-analyzer starts successfully for a Rust project
- [ ] Go-to-definition returns correct file/line for a function call
- [ ] Find-references returns all usages of a function
- [ ] Hover returns type information
- [ ] LSP server shuts down cleanly when Nala exits
- [ ] If no LSP server is available, graceful degradation (no crash)
