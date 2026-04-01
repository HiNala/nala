# Nala: Master Plan

> **Working name:** Nala. All code references use `APP_NAME` constant. Rename is a single-line change.

---

## The Vision in Plain English

Nala is a terminal-first, AI-powered coding environment built from the ground up for speed, quality, and large-codebase mastery. It is not a VS Code fork. It is not a wrapper around someone else's editor. It is a purpose-built tool that combines:

- **NeoVim** — keyboard-driven speed, modal philosophy, terminal as home
- **OpenCode** — SSH-style terminal boot, Go/Rust TUI, client/server architecture, multi-session
- **Cursor** — semantic codebase indexing, sub-agent orchestration, multi-file edits, plan-then-build
- **CodeRabbit** — AI-powered code reviews with AST understanding, graph-based dependency analysis

When you type `nala` and hit Enter, you drop into a clean, dark, polished terminal interface. No Electron. No browser. No 800MB RAM just to open a project. You are in your codebase, and Nala understands it deeply because it has already indexed every function, class, module, import, and dependency into a fast, queryable graph.

---

## Why Nala Exists

**Cursor / Windsurf:** Built on VS Code → Electron bloat, sluggish startup, heavy RAM consumption. Not terminal-native. Not built for developers who demand speed above all.

**Claude Code / OpenCode:** Fast and terminal-native, but conversation-first. They do not build a persistent, structured graph of your codebase. They do not offer multi-perspective analysis. They wait for you to ask rather than showing you where problems are.

**CodeRabbit:** Excellent at AI code review, but lives in the PR workflow. Reviews happen after you push. Nala brings that same depth into your local loop before you ever commit.

**NeoVim:** Blazing fast and keyboard-driven, but AI integration requires extensive plugin configuration and community scripts. Its power is hidden behind a steep learning curve.

Nala sits in the middle. Terminal-native. Blazing fast. AI-aware from the foundation. It gives you a structured, multi-perspective view of your codebase with the speed of NeoVim, the intelligence of Cursor, the code-review depth of CodeRabbit, and the clean SSH-style boot of OpenCode.

---

## Who Nala Is For

- Developers who work on large, complex codebases
- People tired of switching between five different tools for a clear picture of project health
- Developers who value speed, keyboard-driven workflows, and professional aesthetics
- Solo developers and small teams who want enterprise-grade analytical depth without bloat or price

---

## Core Design Philosophy

Drawn from Alan Kay (systems that reveal how they work), Dieter Rams (honest, unobtrusive, long-lasting design), Linus Torvalds (pragmatic robustness), Ken Thompson & Dennis Ritchie (composability and minimalism), and Steve Jobs (ruthless simplification with moments of delight):

1. **Terminal is home.** Everything happens there. Optional GUI layers exist but are never required.
2. **Speed is non-negotiable.** If it takes more than a second to respond, it is too slow.
3. **The codebase is a graph, not a pile of files.** Every symbol is a node, every relationship is an edge.
4. **Analysis happens through perspectives.** Complexity, dependencies, coverage, churn, dead code, performance — each is a lens applied to the graph.
5. **Sessions are sacred.** Every analysis run creates a structured session directory. Nothing is lost.
6. **The user is in control.** Nala guides but never forces. It suggests but never overwrites without confirmation.
7. **Extensibility is architecture, not an afterthought.** New perspectives, new LLM providers, new languages plug in without rewriting the core.
8. **Files stay under 400-600 lines.** Every source file follows this rule. If it grows beyond, split it.

---

## Technology Stack

### Rust Core Engine (Performance Layer)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Parsing | tree-sitter | Incremental AST parsing, 100+ languages |
| Metrics | rust-code-analysis (Mozilla) | Cyclomatic/cognitive complexity, Halstead, SLOC |
| TUI | ratatui + crossterm | 60fps double-buffered terminal rendering |
| LSP | tower-lsp / lsp-types | go-to-definition, find-references, diagnostics |
| Storage | rusqlite (SQLite) | Persistent index cache, session storage |
| Hashing | sha2 | Content hashing for incremental indexing |
| File walking | walkdir | Recursive directory traversal |
| Parallelism | rayon | Parallel file processing |
| Python bridge | pyo3 + maturin | Expose Rust APIs as native Python module |

### Python Orchestration Layer (Intelligence Layer)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Code graph | Neo4j + neo4j Python driver | Relationship traversal, Cypher queries |
| LLM providers | anthropic, openai, google-generativeai | Claude, GPT, Gemini, Ollama |
| Analysis | Custom perspectives engine | Complexity, deps, coverage, churn, dead code |
| Sessions | File-based + SQLite | Markdown reports, mission docs |
| Web server | FastAPI + uvicorn | Optional graph visualization dashboard |

### How the Layers Connect

```
User input → Ratatui TUI (Rust) → PyO3 bridge → Python orchestrator
                                                      ↓
                                              Neo4j graph query
                                              LLM provider call
                                              Perspective engine
                                                      ↓
                                              Structured results
                                                      ↓
                                         Ratatui TUI renders results
```

For pure indexing/parsing: Rust handles everything natively (no Python involved).
For orchestration, AI calls, graph queries: Python coordinates via the PyO3 bridge.

---

## Feature Map

### Phase 1: Foundation (Missions 01-06)
1. SSH-style terminal boot — `nala` → instant clean interface
2. Codebase indexing engine — Tree-sitter parsing, content hashing, SQLite cache
3. Terminal user interface — Ratatui, collapsible panels, command prompt
4. Code navigation — jump to definition, find references, symbol search
5. Pre-analysis chunking — interactive section selection before analysis
6. Session management — `.nala/` directory, timestamped reports

### Phase 2: Analysis Perspectives (Missions 07-09)
7. Complexity perspective — cyclomatic + cognitive complexity per function
8. Dependency perspective — coupled modules, circular deps, critical chains
9. Test coverage perspective — untested code mapped to the dependency graph
10. Code churn perspective — git history analysis, high-churn risk hotspots
11. Dead code perspective — defined-but-never-referenced symbols
12. Performance perspective — anti-patterns, profiling integration

### Phase 3: Agent Actions and Reports (Missions 10-12)
13. Audit report generation — comprehensive markdown with findings ranked by severity
14. Mission generation — self-contained task documents from audit findings
15. Inline agent actions — refactor/fix commands from inside the TUI

### Phase 4: Dashboard and Polish (Mission 13)
16. Optional web dashboard — FastAPI + D3.js Neo4j graph visualization

### Phase 5: Future Vision (Mission 14)
17. Custom model integration — fine-tuned models for specialized analysis
18. MCP server support — expose Nala's capabilities to other AI tools
19. Collaborative features — shared sessions, team dashboards, GitHub/GitLab integration

---

## Project Structure

```
nala/
├── README.md
├── LICENSE
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml
├── rust-core/
│   ├── Cargo.toml                  # Workspace manifest
│   ├── nala-cli/                   # Binary entry point
│   │   ├── Cargo.toml
│   │   └── src/
│   │       └── main.rs
│   ├── nala-tui/                   # Ratatui TUI
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── app.rs
│   │       └── ui/
│   │           ├── mod.rs
│   │           ├── layout.rs
│   │           ├── command_bar.rs
│   │           ├── file_panel.rs
│   │           ├── session_panel.rs
│   │           ├── status_bar.rs
│   │           └── splash.rs
│   ├── nala-indexer/               # Tree-sitter + metrics
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── scanner.rs
│   │       ├── hasher.rs
│   │       ├── parser.rs
│   │       ├── metrics.rs
│   │       ├── symbol_graph.rs
│   │       └── cache.rs
│   ├── nala-lsp/                   # LSP client
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── client.rs
│   │       └── config.rs
│   └── nala-bridge/                # PyO3 bindings
│       ├── Cargo.toml
│       ├── pyproject.toml
│       └── src/
│           └── lib.rs
├── python-orchestrator/
│   ├── pyproject.toml
│   └── nala_orchestrator/
│       ├── __init__.py
│       ├── config.py
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── connection.py
│       │   ├── schema.py
│       │   ├── queries.py
│       │   └── builder.py
│       ├── perspectives/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── complexity.py
│       │   ├── dependency.py
│       │   ├── coverage.py
│       │   ├── churn.py
│       │   ├── dead_code.py
│       │   └── performance.py
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── provider.py
│       │   ├── anthropic_provider.py
│       │   ├── openai_provider.py
│       │   ├── google_provider.py
│       │   └── ollama_provider.py
│       ├── sessions/
│       │   ├── __init__.py
│       │   ├── manager.py
│       │   ├── report.py
│       │   └── missions.py
│       └── agents/
│           ├── __init__.py
│           ├── orchestrator.py
│           └── actions.py
├── dashboard/
│   ├── requirements.txt
│   ├── server.py
│   └── static/
│       ├── index.html
│       └── graph.js
└── docs/
    ├── missions/
    │   ├── MISSION_00_MASTER_PLAN.md  (this file)
    │   ├── MISSION_01_SETUP.md
    │   └── ... (all 19 missions)
    ├── ARCHITECTURE.md
    ├── DATA_FLOW.md
    └── EXTENSION_GUIDE.md
```

---

## Mission Index

| # | Mission | Status |
|---|---------|--------|
| 01 | Project Setup and Scaffolding | ⬜ |
| 02 | File Scanner and Content Hasher | ⬜ |
| 03 | Tree-sitter Parser and Metrics Engine | ⬜ |
| 04 | TUI Shell and Boot Experience | ⬜ |
| 05 | LSP Client Integration | ⬜ |
| 06 | PyO3 Bridge and Python Scaffold | ⬜ |
| 07 | Neo4j Code Graph and Symbol Population | ⬜ |
| 08 | Pre-Analysis Chunking and Interactive Selection | ⬜ |
| 09 | Analysis Perspectives Engine | ⬜ |
| 10 | Session Management and Report Generation | ⬜ |
| 11 | Mission Document Auto-Generation | ⬜ |
| 12 | LLM Provider Integration | ⬜ |
| 13 | Inline Agent Actions | ⬜ |
| 14 | Optional Web Dashboard | ⬜ |
| 15 | Review, Polish, and Harden | ⬜ |
| 16 | What's Next (Future Vision and Roadmap) | ⬜ |
| 17 | System Architecture Deep Dive | ⬜ |
| 18 | Data Flow and Integration Patterns | ⬜ |
| 19 | Extension Points and Plugin System | ⬜ |

---

## Success Criteria

Nala is successful when a developer can:

1. Type `nala` in a terminal and be inside a polished, responsive coding environment within **2 seconds**
2. Index a 100,000-line codebase in **under 30 seconds** on first run, under 2 seconds on subsequent runs
3. Navigate to any function definition in **under 100ms**
4. Run a multi-perspective analysis and receive a structured markdown report within **60 seconds**
5. Generate actionable mission documents from the analysis that can be handed to Claude Code or another coding agent
6. Feel like the tool was built by someone who **genuinely cares** about developer experience

---

## Naming

"Nala" is a working name. All references in code use `APP_NAME` constant in `nala-cli/src/constants.rs`. Renaming is a single change in that file.
