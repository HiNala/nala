# Mission 17: Architecture - System Architecture Deep Dive

## Objective

Produce a comprehensive ARCHITECTURE.md document that explains every layer, crate, module, and component of Nala's architecture in plain English. This document should be detailed enough that a new engineer (or an AI coding agent) can understand the entire system without reading the source code. It should explain not just what each component does, but why it exists, how it connects to other components, and what design decisions were made along the way.

## Why This Matters

Architecture documentation is the difference between a project that can survive its creator leaving and one that cannot. It is also the difference between an AI coding agent that can make intelligent changes across the codebase and one that blindly modifies files without understanding the consequences. This document is the single source of truth for "how does Nala work?"

## Document Structure

### Section 1: System Overview

A high-level description of Nala's four-layer architecture:

**Layer 1 - File System**: The raw codebase on disk. Nala never modifies the user's code without explicit confirmation. The only thing Nala writes to the project directory is the `.nala/` metadata folder.

**Layer 2 - Rust Core**: Five Cargo crates that handle everything performance-critical. Explain each crate:

- `nala-cli`: The binary entry point. Parses CLI arguments with clap. Decides whether to launch the TUI, run a single command (scan, index, dashboard), or print help. This crate is intentionally thin; it delegates to other crates immediately.

- `nala-tui`: The terminal user interface. Built on Ratatui + crossterm. Manages the app state machine (Booting -> Ready -> Command -> Analyzing -> Viewing). Owns the event loop, keyboard/mouse handling, panel rendering, command bar, and status bar. Does not contain business logic; it calls into nala-indexer for data and dispatches to the Python layer for analysis.

- `nala-indexer`: The core intelligence of the Rust side. Contains: Scanner (walkdir-based file discovery with filters), Hasher (SHA-256 content hashing with Rayon parallelism), Parser (Tree-sitter multi-language parsing), SymbolExtractor (AST walking to extract functions/classes/imports/calls), MetricsEngine (rust-code-analysis integration for CC/cognitive/Halstead), Cache (SQLite storage for incremental indexing). This crate's API is: give me a directory path, and I will give you back every symbol, every metric, and every relationship in it, fast.

- `nala-lsp`: Language Server Protocol client. Manages multiple LSP server processes (one per language). Handles the JSON-RPC protocol, file synchronization, and diagnostics caching. Provides go-to-definition, find-references, hover, and document-symbols functionality.

- `nala-bridge`: PyO3 bridge. Exposes nala-indexer's data types and functions as a Python module called `nala_core`. Converts Rust types to Python types in bulk batches to minimize cross-language overhead. This is the seam between the Rust performance layer and the Python intelligence layer.

**Layer 3 - Python Orchestration**: A Python package (`nala_orchestrator`) that handles everything requiring flexibility, AI integration, and complex business logic:

- `config`: Configuration management. Loads from `.nala/config.toml`, environment variables, and CLI flags, in that priority order.

- `graph/`: Neo4j integration. Connection management, schema definitions, batch data loading, and pre-built Cypher queries for common analysis patterns.

- `perspectives/`: The analytical engine. Each perspective is a self-contained class that takes indexed data and graph connections as input and produces structured findings as output. Perspectives are composable and can be run individually or in combination.

- `llm/`: LLM provider abstraction. Supports multiple providers through a common interface. Handles prompt construction, context injection, streaming responses, and error handling.

- `sessions/`: Session lifecycle management. Creates timestamped session directories, saves analysis results and reports, supports session comparison for tracking progress over time.

- `agents/`: Agent orchestration for inline code modifications. Gathers context from the graph and metrics, constructs prompts, parses proposed changes, and manages the user confirmation flow.

**Layer 4 - Web Dashboard**: An optional FastAPI server with a D3.js frontend for graph visualization. Reads from Neo4j and the session history. Runs on localhost only.

### Section 2: Crate Dependency Graph

A text-based diagram showing which Rust crates depend on which:

```
nala-cli
  ├── nala-tui
  │     └── nala-indexer
  └── nala-indexer

nala-bridge
  └── nala-indexer

nala-lsp (standalone, connected via nala-tui at runtime)
```

Explain why the graph is structured this way: nala-indexer is the shared core, nala-tui adds the interface layer, nala-bridge adds the Python binding layer, and nala-cli ties it together as the entry point.

### Section 3: Key Design Decisions

Document each major design decision with the format: Decision, Alternatives Considered, Why We Chose This.

- Why Rust + Python instead of all Rust or all Python?
- Why Ratatui instead of Go's Bubble Tea or Python's Textual?
- Why Tree-sitter instead of language-specific parsers?
- Why Neo4j instead of an in-memory graph or SQLite?
- Why PyO3 instead of gRPC or REST for the Rust-Python bridge?
- Why SQLite for caching instead of Redis or flat files?
- Why content hashing instead of file modification timestamps?

### Section 4: Error Handling Strategy

Document the error handling approach:
- Rust uses `thiserror` for library crates and `anyhow` for the CLI/TUI
- Python uses custom exception classes derived from a base `NalaError`
- Every error includes: what happened, where it happened, and what the user can do about it
- Neo4j disconnection is never fatal; features gracefully degrade
- LLM API failures are never fatal; the tool works without AI
- File system errors are caught per-file; one unreadable file does not stop the scan

### Section 5: Threading and Concurrency Model

Document how concurrency works:
- The TUI event loop runs on the main thread (tokio single-threaded runtime)
- File scanning and hashing run on Rayon's thread pool (CPU-bound parallelism)
- LSP server communication runs on tokio async tasks
- The Python orchestration layer runs in a separate thread (to avoid blocking the TUI)
- Neo4j queries are I/O-bound and run async

## Acceptance Criteria

- ARCHITECTURE.md is comprehensive enough for a new engineer to understand the system
- Every crate, module, and key class is documented
- Design decisions are explained with alternatives and rationale
- No architectural aspect is left unexplained

---

# Mission 18: Architecture - Data Flow and Integration Patterns

## Objective

Produce a DATA_FLOW.md document that traces every data flow through the system, from raw files on disk to rendered TUI output and saved session reports. This document answers: "When I type `/analyze complexity`, what exactly happens?"

## Document Structure

### Flow 1: Boot and Initial Indexing

1. User types `nala` in terminal
2. nala-cli parses args, determines project root
3. nala-tui initializes the terminal (raw mode, alternate screen)
4. Splash screen renders while background indexing starts
5. nala-indexer::Scanner walks the file system, collects ScannedFile list
6. nala-indexer::Hasher computes SHA-256 for each file (parallel via Rayon)
7. nala-indexer::Cache compares hashes to SQLite, identifies changed files
8. nala-indexer::Parser parses changed files with Tree-sitter (parallel)
9. nala-indexer::SymbolExtractor walks ASTs, extracts symbols
10. nala-indexer::MetricsEngine computes complexity metrics
11. Results stored in SQLite cache
12. TUI status bar updates with file count and stats
13. Splash transitions to main workspace

### Flow 2: Graph Population

1. User types `/graph init` or it runs automatically after indexing
2. TUI dispatches to Python via PyO3 bridge
3. nala-bridge converts Rust IndexResult to Python types
4. nala_orchestrator.graph.builder receives symbol data
5. GraphBuilder connects to Neo4j
6. GraphBuilder runs batch Cypher queries to create nodes and relationships
7. GraphBuilder returns success/failure to TUI
8. TUI shows "Graph populated: X nodes, Y relationships"

### Flow 3: Analysis with Perspective Selection

1. User types `/analyze`
2. Python chunking module computes codebase sections
3. TUI presents interactive section selection
4. User selects sections
5. Python perspective runner instantiates selected perspectives
6. Each perspective queries the graph, metrics, and/or git history
7. Findings are collected, deduplicated, and sorted
8. AnalysisResult returned to TUI for display
9. SessionManager saves session data and generates report
10. MissionGenerator produces mission documents
11. TUI shows executive summary and session path

### Flow 4: Natural Language Query

1. User types "What functions call process_payment?"
2. TUI detects non-slash-command input
3. Python LLM provider constructs prompt with codebase context
4. Context includes: relevant symbols from graph query, metrics for matched functions, file paths
5. Prompt sent to configured LLM (Claude/OpenAI/Ollama)
6. Response streams back token-by-token
7. TUI renders streaming response in the main area

### Flow 5: Agent Action

1. User selects a finding and types "fix this"
2. Python agent orchestrator gathers context: function code, metrics, callers, tests
3. Constructs a prompt asking the LLM for a specific code change
4. LLM returns proposed diff
5. TUI displays the diff with syntax highlighting
6. User confirms, rejects, or edits
7. If confirmed, agent writes the modified file to disk
8. Action is recorded in session history

### Flow 6: Dashboard Launch

1. User types `/dashboard`
2. Python starts FastAPI server in a background thread
3. Server listens on localhost:3000
4. TUI opens the user's default browser to localhost:3000
5. Browser loads index.html, fetches /api/graph
6. D3.js renders the force-directed graph
7. User interacts with the graph in the browser
8. `/dashboard stop` sends shutdown signal to the FastAPI server

### Integration Patterns

Document the three integration patterns used in Nala:

**PyO3 Bridge Pattern**: Rust -> Python function calls. Used for all data transfer from the indexer to the orchestration layer. Data is serialized in Rust, deserialized in Python. Always batch operations, never per-item calls.

**Async Dispatch Pattern**: TUI -> background task. The TUI dispatches long-running operations (indexing, analysis, LLM calls) as async tasks and shows progress indicators while waiting.

**Event-Driven Pattern**: Background processes (file watcher, LSP diagnostics) push events to the TUI's event channel. The TUI processes events on each frame.

## Acceptance Criteria

- Every major user action is traced from input to output
- Data transformations at each step are documented
- Integration patterns are clearly explained
- The document enables a developer to debug any flow by following the trace

---

# Mission 19: Architecture - Extension Points and Plugin System

## Objective

Produce an EXTENSION_GUIDE.md document that explains every point in Nala's architecture where external code can be plugged in. This covers custom perspectives, custom LLM providers, custom language support, custom TUI themes, and the future plugin system. The goal is to make Nala extensible without requiring changes to the core codebase.

## Document Structure

### Extension Point 1: Custom Perspectives

Explain how to write a custom perspective:

1. Create a Python file in `~/.nala/perspectives/` or in the project's `.nala/perspectives/`
2. Define a class that inherits from `nala_orchestrator.perspectives.base.Perspective`
3. Implement the `analyze()` method
4. Nala automatically discovers and loads custom perspectives on startup
5. Custom perspectives appear in the `/analyze` menu alongside built-in ones

Provide a complete example: a "naming conventions" perspective that checks if function names follow snake_case and class names follow PascalCase.

### Extension Point 2: Custom LLM Providers

Explain how to add a new LLM provider:

1. Create a Python file implementing the `LLMProvider` interface
2. Register it in the config with a custom provider name
3. Nala loads it via the provider factory

Provide an example: a provider that calls a custom corporate API.

### Extension Point 3: Custom Language Support

Explain how to add a new language to the indexer:

1. Add the Tree-sitter grammar crate to nala-indexer's Cargo.toml
2. Implement the `LanguageExtractor` trait for the new language
3. Add the file extension mapping to `detect_language()`
4. Add LSP server configuration to the default config

### Extension Point 4: Custom TUI Themes

Explain how to customize the TUI appearance:

1. Create a theme TOML file at `~/.nala/theme.toml`
2. Define colors for: background, foreground, accent, error, warning, success, panel borders, status bar
3. Nala loads the theme on startup

### Extension Point 5: MCP Server (Future)

Document the planned MCP server extension point:

1. Nala exposes its capabilities as MCP tools
2. Other AI tools can call Nala's indexer, graph, and perspectives
3. Configuration via `.nala/mcp.toml`

### Extension Point 6: Hooks

Document planned lifecycle hooks:

- `on_scan_complete`: Called after file scanning, receives scan results
- `on_index_complete`: Called after indexing, receives index results  
- `on_analysis_complete`: Called after analysis, receives findings
- `on_session_save`: Called when a session is saved

Hooks are Python scripts in `.nala/hooks/` that Nala executes at the appropriate time. They can be used for custom notifications, integrations with other tools, or additional processing.

## Acceptance Criteria

- Every extension point is documented with a working example
- The guide is clear enough for a developer to add a custom perspective in under 30 minutes
- Extension points do not require modifying Nala's core source code
- The document covers both current extension points and planned future ones
