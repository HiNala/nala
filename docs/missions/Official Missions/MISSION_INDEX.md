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
| MISSION_20_context_window_management.md | 20 | Token tracking, auto-compaction, context window controls |
| MISSION_21_hierarchical_memory.md | 21 | Short-term, session, and knowledge-base memory layers |
| MISSION_22_session_handoff.md | 22 | Structured handoff documents for session continuity |
| MISSION_23_multi_agent_orchestration.md | 23 | Multi-agent team coordination with task decomposition |
| MISSION_24_context_compression.md | 24 | Advanced compression pipeline for context efficiency |
| MISSION_25_objective_driven_agent.md | 25 | Proactive startup, git awareness, task ledger, action pipeline |
| MISSION_26_brain_mode_optional_workflow.md | 26 | Optional Brain Mode workflow, orchestration layer, scoped memory/rules |
| MISSION_27_agent_command_surface_consolidation.md | 27 | Consolidate Brain Mode and overlapping commands under `/agent` |
| MISSION_28_agent_control_plane.md | 28 | Build the central `/agent` runtime and durable control plane |
| MISSION_29_agent_workbench_tui.md | 29 | Add an optional `/agent` workbench inside the TUI |
| MISSION_30_agent_autonomous_workflow_loop.md | 30 | Implement the full `/agent` plan, approve, execute, verify, review loop |
| MISSION_31_agent_skills_scoped_memory_and_safe_autonomy.md | 31 | Add durable `/agent` memory, skills, scoped rules, and safe autonomy |
| MISSION_32_interpreter_orchestrator_worker_architecture.md | 32 | Formalize the interpreter, orchestrator, and worker runtime architecture |
| MISSION_33_spawned_agent_terminals_and_attach_flow.md | 33 | Spawn worker terminals and support attach, inspect, and takeover flows |
| MISSION_34_git_integration_worktrees_and_review_flow.md | 34 | Add deeper git integration, worktrees, and review-oriented SCM flows |
| MISSION_35_web_search_and_live_research_grounding.md | 35 | Add bounded live web research and cited external context to `/agent` |
| MISSION_36_human_in_loop_orchestration_experience.md | 36 | Design the full interpreter plus orchestrator plus worker human-in-the-loop UX |

## Execution Order

**Phase 1 - Foundation (Missions 01-06)**: Get the core running. After these missions, Nala boots, scans, indexes, parses, and bridges data to Python.

**Phase 2 - Intelligence (Missions 07-10)**: Add the analytical brain. After these missions, Nala understands the codebase as a graph, runs multi-perspective analysis, and generates session reports.

**Phase 3 - AI and Actions (Missions 11-14)**: Add AI-powered features. After these missions, Nala generates mission documents, answers natural language questions, applies agent fixes, and optionally visualizes the graph in a browser.

**Phase 4 - Quality (Missions 15-16)**: Polish everything. After these missions, Nala is production-ready and has a clear roadmap.

**Phase 5 - Documentation (Missions 17-19)**: Document the architecture for maintainability and extensibility. After these missions, any engineer or AI agent can understand and extend Nala.

**Phase 5B - Context & Memory (Missions 20-24)**: Add intelligent context management, hierarchical memory, session handoffs, multi-agent coordination, and compression. After these missions, Nala maintains deep continuity across sessions.

**Phase 6 - Objective-Driven Agent (Mission 25+)**: Transform Nala from a chat tool into a goal-oriented coding agent with proactive startup, git awareness, task tracking, and safe action pipelines.

**Phase 6B - Brain Mode (Mission 26+)**: Add an optional deep-reasoning workflow with explicit plan/approve/execute/verify loops, scoped instructions, and durable Brain artifacts.

**Phase 6C - `/agent` Unification (Missions 27-31)**: Rename Brain Mode to `/agent`, simplify the command surface, build a central control plane, expose a focused TUI workbench, implement the real autonomous workflow loop, and add durable skills, scoped memory, and safety boundaries.

**Phase 6D - Terminal Orchestration (Missions 32-36)**: Formalize the interpreter-orchestrator-worker model, spawn and manage worker terminals, add deeper git/worktree support, integrate live web research, and design the full human-in-the-loop orchestration experience.

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
