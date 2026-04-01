# Nala: System Architecture

## Overview

Nala is a hybrid Rust/Python application with four distinct layers:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: Optional Web Dashboard (FastAPI + D3.js)          │
│  — localhost:3000 — graph visualisation — optional          │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Python Orchestration (nala_orchestrator)          │
│  — LLM providers — Neo4j graph — perspectives — sessions    │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Rust Core (nala-* crates)                         │
│  — TUI — indexer — LSP — PyO3 bridge                        │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Foundation                                        │
│  — File system — SQLite cache — .nala/ sessions             │
└─────────────────────────────────────────────────────────────┘
```

## Rust Core Crates

### nala-cli
Entry point binary. Parses CLI args (clap), initialises tokio, dispatches to TUI or subcommands. All constants (APP_NAME, etc.) live here. **Single binary: `nala`.**

### nala-tui
Ratatui-based terminal UI. Owns the async event loop, all rendering, and keyboard/mouse handling. Does not perform heavy computation — it dispatches work to background tokio tasks and renders results. 30fps render loop using double-buffered diff rendering.

**Key files:**
- `app.rs` — state machine (AppMode enum), event dispatch, background task channel
- `ui/layout.rs` — constraint-based layout composition
- `ui/splash.rs` — 1.5-second boot splash

### nala-indexer
The fast path. Everything that does not need AI runs here.
- `scanner.rs` — walkdir-based file discovery with include/exclude filters
- `hasher.rs` — parallel SHA-256 content hashing via Rayon
- `cache.rs` — SQLite (rusqlite) incremental change tracking
- `parser.rs` — Tree-sitter parsing and symbol extraction
- `symbol_graph.rs` — Symbol type hierarchy
- `metrics.rs` — Cyclomatic complexity, SLOC, CLOC

**Key invariant:** indexer operations are pure functions. They take paths and return data. No global state. No side effects beyond SQLite writes.

### nala-lsp
LSP client. Launches language server processes (rust-analyzer, pyright, gopls, etc.) and communicates via JSON-RPC over stdio. Currently stubbed; full implementation in Mission 05.

### nala-bridge
PyO3 native extension module (`nala_core`). Exposes indexer operations to Python. Built with Maturin. Serialises complex types via serde_json to avoid lifetime issues.

## Python Orchestration

### Config
Pydantic-based configuration loaded from `.env` file. Single source of truth for: LLM provider, API keys, Neo4j URI, project root.

### LLM Providers
Abstract `BaseLLMProvider` with four implementations: Anthropic, OpenAI, Google, Ollama. Factory pattern via `create_provider(config)`. All providers implement `chat()` and `stream_chat()`.

### Graph Layer
Neo4j driver with graceful degradation (Nala works without it). `GraphBuilder` populates File/Function/Class nodes from indexer output. `GraphConnection.run()` executes Cypher queries.

### Perspectives Engine
Each perspective is a class extending `BasePerspective`. Perspectives that don't need Neo4j (like complexity) read from the SQLite cache. Perspectives that traverse relationships (like dependency, dead code) require Neo4j.

### Session Manager
Creates `.nala/sessions/{timestamp}/` directories. Writes markdown reports and mission documents. Provides list/load/resume operations for the TUI.

### Agent Orchestrator
Manages conversation history. Builds system prompts with project context (file count, symbol count, language). Routes queries to the active LLM provider. Handles streaming responses.

## Data Flow

See [DATA_FLOW.md](DATA_FLOW.md) for the complete step-by-step data flow.

## Design Decisions

**Why Rust + Python (not pure Rust or pure Python)?**
Rust gives us sub-millisecond parsing, parallel hashing, and a polished TUI. Python gives us the AI ecosystem (anthropic SDK, neo4j driver, etc.) and faster iteration on the intelligence layer. PyO3 bridges them cleanly.

**Why SQLite (not just files)?**
SQLite gives us atomic writes, transactions, and fast indexed queries over the file cache. It also means the cache is a single file that's easy to inspect, back up, and delete.

**Why Neo4j (not just SQLite)?**
Relationship traversal (find all files that import module X, find the call chain from function A to function B) is what graph databases are built for. Cypher queries for this are 3 lines; the equivalent SQL would be 50+ lines with recursive CTEs.

**Why Ratatui (not a web UI)?**
The terminal is the developer's home. Sub-millisecond rendering. Zero browser overhead. Works over SSH. Aligns with the core philosophy: terminal is home, speed is non-negotiable.
