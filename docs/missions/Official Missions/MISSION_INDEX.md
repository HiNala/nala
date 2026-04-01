# Nala: Mission Index

## How to Use These Documents

Start with **00_MASTER_PLAN.md**. Read it fully. It explains the vision, architecture, tech stack, feature map, and project structure. Every subsequent mission references concepts from the master plan.

Then execute missions in order. Each mission is self-contained with objectives, implementation steps, and acceptance criteria. Hand each mission to Claude Code (or your preferred coding agent) one at a time. Complete each mission's acceptance criteria before moving to the next.

## Mission Files

| File | Missions | Description |
|------|----------|-------------|
| 00_MASTER_PLAN.md | -- | Complete vision, architecture, tech stack, feature map, project structure |
| MISSION_01_project_setup.md | 01 | Rust workspace, Python package, PyO3 bridge, CI scaffold |
| MISSION_02_scanner_hasher.md | 02 | File system scanner, SHA-256 content hasher, SQLite cache |
| MISSION_03_parser_metrics.md | 03 | Tree-sitter parsing, symbol extraction, code metrics engine |
| MISSION_04_tui_shell.md | 04 | Ratatui TUI, boot splash, panels, command bar, status bar |
| MISSION_05_lsp_client.md | 05 | Language Server Protocol client for code intelligence |
| MISSION_06_pyo3_bridge.md | 06 | PyO3 Rust-Python bridge, Python orchestration scaffold |
| MISSION_07_08_09_10_graph_analysis_sessions.md | 07-10 | Neo4j graph, chunking, analysis perspectives, sessions/reports |
| MISSION_11_12_13_14_missions_llm_agents_dashboard.md | 11-14 | Mission auto-gen, LLM integration, agent actions, web dashboard |
| MISSION_15_16_polish_roadmap.md | 15-16 | Review/polish/harden, future roadmap |
| MISSION_17_18_19_architecture_docs.md | 17-19 | System architecture, data flow, extension points documentation |

## Execution Order

**Phase 1 - Foundation (Missions 01-06)**: Get the core running. After these missions, Nala boots, scans, indexes, parses, and bridges data to Python.

**Phase 2 - Intelligence (Missions 07-10)**: Add the analytical brain. After these missions, Nala understands the codebase as a graph, runs multi-perspective analysis, and generates session reports.

**Phase 3 - AI and Actions (Missions 11-14)**: Add AI-powered features. After these missions, Nala generates mission documents, answers natural language questions, applies agent fixes, and optionally visualizes the graph in a browser.

**Phase 4 - Quality (Missions 15-16)**: Polish everything. After these missions, Nala is production-ready and has a clear roadmap.

**Phase 5 - Documentation (Missions 17-19)**: Document the architecture for maintainability and extensibility. After these missions, any engineer or AI agent can understand and extend Nala.

## Tech Stack Quick Reference

| Layer | Language | Key Libraries |
|-------|----------|--------------|
| Core Engine | Rust | tree-sitter, rust-code-analysis, ratatui, crossterm, rusqlite, sha2, rayon, walkdir |
| Python Bridge | Rust | pyo3 + maturin |
| Orchestration | Python | neo4j, anthropic/openai, fastapi |
| LSP | Rust | tower-lsp / lsp-types, tokio |
| Dashboard | Python/JS | FastAPI, D3.js |

## Key Principles

- No source file over 400-600 lines, ever
- Plain English in all documentation
- Every error message tells the user what to do, not just what went wrong
- Terminal-first, browser-optional
- Speed is non-negotiable (sub-second for navigation, under 30s for initial indexing)
- The user is always in control (no auto-modifications without confirmation)
