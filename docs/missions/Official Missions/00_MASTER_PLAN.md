# Nala: Master Plan

## The Vision in Plain English

Nala is a terminal-first, AI-powered coding environment built from the ground up for speed, quality, and large-codebase mastery. It is not a VS Code fork. It is not a wrapper around someone else's editor. It is a purpose-built tool that combines the best ideas from NeoVim (keyboard-driven speed, modal editing), OpenCode (SSH-style terminal boot, Go/Rust TUI, client/server architecture, multi-session support, LSP integration), Cursor (semantic codebase indexing, sub-agent orchestration, multi-file edits, plan-then-build workflow), and CodeRabbit (AI-powered code reviews with AST understanding, graph-based dependency analysis) into a single, cohesive experience that feels like a professional instrument, not a toy.

When you type `nala` in your terminal and hit Enter, you are dropped into a clean, dark, polished terminal interface. No Electron. No browser. No 800MB of RAM just to see your files. You are in your codebase, and Nala understands it deeply because it has already indexed every function, class, module, import, and dependency into a fast, queryable graph.

---

## Why Nala Exists

Every existing tool falls short in at least one critical way.

Cursor and Windsurf are built on VS Code, which means they inherit Electron's bloat, its sluggish startup, and its heavy resource consumption. They are not built for the developer who wants terminal-native speed above all else. They eat RAM. They are slow to boot. They feel like web apps pretending to be native software.

Claude Code and OpenCode are fast and terminal-native, but they are conversation-first tools. They are reactive, not proactive. They do not build a persistent, structured graph of your codebase. They do not offer multi-perspective analysis that generates actionable mission documents. They wait for you to ask a question rather than showing you where the problems are.

CodeRabbit is excellent at AI code review, but it lives in the PR workflow. It reviews changes after you push. Nala brings that same depth of analysis into your local development loop before you ever commit.

NeoVim is blazing fast and keyboard-driven, but it requires extensive plugin configuration and community scripts to approach anything resembling modern AI assistance. Its power is hidden behind a steep learning curve and fragmented ecosystem.

Nala sits in the middle of all of these. It is terminal-native. Blazing fast. AI-aware from the foundation. It gives you a structured, multi-perspective view of your codebase with the speed of NeoVim, the intelligence of Cursor, the code-review depth of CodeRabbit, and the clean SSH-style boot of OpenCode.

---

## Who Nala Is For

Nala is for developers who work on large, complex codebases and want a single, cohesive tool that helps them understand, analyze, and improve their code. It is for people who are tired of switching between five different tools just to get a clear picture of their project's health. It is for developers who value speed, keyboard-driven workflows, and a professional aesthetic. It is for solo developers and small teams who want the analytical depth of enterprise tooling without the enterprise price tag or bloat.

---

## Core Design Philosophy

These are the principles that guide every decision in Nala's design, drawn from the best thinking of Alan Kay (systems that reveal how they work), Dieter Rams (honest, unobtrusive, long-lasting design), Linus Torvalds (pragmatic robustness over theoretical elegance), Ken Thompson and Dennis Ritchie (composability and minimalism), and Steve Jobs (ruthless simplification with moments of delight).

1. Terminal is home. The terminal is the primary workspace. Everything happens there. Optional GUI layers (a web dashboard for graph visualization) can be added, but the terminal is never abandoned.

2. Speed is non-negotiable. If it takes more than a second to respond, it is too slow. The Rust core engine ensures sub-millisecond parsing and indexing. The TUI renders at 60fps with Ratatui's double-buffered diff rendering.

3. The codebase is a graph, not a pile of files. Every function, class, module, import, and dependency is a node in a structured graph. Relationships between them are edges. This graph is the foundation for every perspective, every analysis, and every recommendation Nala makes.

4. Analysis happens through perspectives. A perspective is a specific analytical lens applied to the codebase graph. Complexity analysis, dependency mapping, test coverage gaps, code churn hotspots, dead code detection, and performance bottlenecks are all perspectives. The user picks which ones to run.

5. Sessions are sacred. Every analysis run creates a structured session directory with markdown reports, findings, and actionable missions. Nothing is lost. Everything is traceable.

6. The user is in control. Nala guides but never forces. It suggests but never overwrites. It asks "do you want to analyze the whole thing, or pick specific parts?" and lets the user drive.

7. Extensibility is architecture, not an afterthought. The modular design means new perspectives, new LLM providers, new analysis tools, and eventually custom fine-tuned models can be plugged in without rewriting the core.

8. Files stay under 400-600 lines. Every source file in Nala itself follows this rule for maintainability. If a file is getting longer, it gets split. No exceptions.

---

## Technology Stack

### Rust Core Engine (Performance Layer)

The Rust core handles everything that needs to be fast. This is the engine room.

- Tree-sitter for incremental code parsing across all major languages. Tree-sitter builds a concrete syntax tree and can update it in sub-millisecond time when files change. It supports 100+ languages through grammar modules.
- rust-code-analysis (Mozilla) for computing metrics like cyclomatic complexity, cognitive complexity, Halstead metrics, lines of code (SLOC/PLOC/LLOC/CLOC), and maintainability index. This library is built on Tree-sitter and supports 10+ languages.
- Ratatui for the terminal user interface. Ratatui is the most mature Rust TUI framework with 19k+ GitHub stars. It uses immediate-mode rendering with double-buffered diffs, meaning only changed characters are sent to the terminal. Sub-millisecond render times. Supports charts, tables, sparklines, gauges, scrollable lists, and custom widgets.
- tower-lsp for Language Server Protocol integration. This lets Nala connect to any LSP server (rust-analyzer, pyright, typescript-language-server, gopls, etc.) to get go-to-definition, find-references, hover info, and diagnostics. This is how OpenCode and Claude Code achieve code intelligence, and Nala will use the same approach.
- SQLite (via rusqlite) for persistent session storage, codebase index caching, and configuration. Lightweight, embedded, zero-configuration.
- Content hashing (SHA-256) for incremental indexing. Only re-index files whose content hash has changed since the last scan.

### Python Orchestration Layer (Intelligence Layer)

Python handles the higher-level logic, AI integration, and workflow orchestration. It connects to the Rust core via PyO3 (Rust-to-Python bindings built with Maturin).

- PyO3 + Maturin for calling Rust functions from Python. The Rust core exposes its indexing, parsing, and metrics APIs as a native Python module. This means Python gets Rust speed for the heavy lifting while keeping its flexibility for orchestration.
- Neo4j (via neo4j Python driver) for the code knowledge graph. Functions, classes, modules, imports, calls, and dependencies are stored as nodes and relationships. Cypher queries power the analytical perspectives. Neo4j's browser and Bloom tools provide optional graph visualization.
- LLM provider abstraction layer supporting Anthropic (Claude), OpenAI, Google (Gemini), local models via Ollama, and any OpenAI-compatible API. The user picks their provider and model.
- Rich or Textual (optional) for Python-side terminal enhancements if needed, though the primary TUI is Ratatui in Rust.
- FastAPI (optional) for spinning up a lightweight local web dashboard to visualize the Neo4j graph in a browser.

### How the Layers Connect

The user interacts with the Ratatui TUI (Rust). When the user issues a command like "analyze complexity," the Rust TUI dispatches the request to the Python orchestration layer via PyO3. The Python layer coordinates the analysis: it queries the Neo4j graph, applies perspective-specific logic, optionally calls an LLM for deeper insights, and returns structured results. The Rust TUI renders those results in real time.

For pure indexing and parsing operations (scanning files, building the AST, computing metrics), the Rust core handles everything natively without touching Python. Python only enters the picture for orchestration, AI calls, and graph queries.

---

## Feature Map

### Phase 1: MVP (Missions 01-06)

These features get Nala to a usable state where you can boot it up, index a codebase, navigate it, run basic analysis, and see results.

1. SSH-style terminal boot. Type `nala` and you are in. Clean dark interface. Progress bar during first-time indexing. ASCII art logo or minimal branding.

2. Codebase indexing engine. Scans all files in the project directory. Parses each file with Tree-sitter. Computes content hashes for incremental updates. Stores the parsed symbol graph (functions, classes, modules, imports, calls) in both SQLite (for fast local queries) and Neo4j (for relationship traversal).

3. Terminal user interface. Built with Ratatui. Main area is a chat/command prompt (like Claude Code / OpenCode). Optional collapsible side panels: left panel for file tree navigation, right panel for session summaries or graph overview. All panels are togglable so the user builds their workspace the way they want it.

4. Code navigation. Jump to any function, class, or module by typing its name. Go-to-definition via LSP integration. Find all references. Search across the entire codebase by symbol name, file name, or free text.

5. Pre-analysis and chunking. Before running a full analysis, Nala performs a pre-scan that breaks the codebase into logical sections (by module, by feature area, by directory structure). It presents these chunks to the user and asks: "Do you want to analyze everything, or pick specific sections?" This makes the experience interactive and fun rather than a dry batch job.

6. Session management. Every analysis run creates a `.nala/` directory inside the project root. Inside that, each session gets its own timestamped subdirectory with markdown reports, findings, and generated missions. The user can revisit any session, compare sessions over time, and hand off session documents to other tools or team members.

### Phase 2: Analysis Perspectives (Missions 07-09)

These features add the multi-perspective analytical engine that makes Nala genuinely powerful.

7. Complexity perspective. Measures cyclomatic complexity and cognitive complexity per function and per module. Flags functions above configurable thresholds. Generates a ranked list of the most complex areas in the codebase.

8. Dependency perspective. Traverses the Neo4j graph to map all imports, calls, and module relationships. Identifies tightly coupled modules, isolated code paths, circular dependencies, and critical dependency chains where a single change could ripple through the system.

9. Test coverage perspective. Integrates with the project's test runner (or reads coverage reports) to identify untested code. Maps coverage data onto the code graph so you can see which parts of the dependency tree are unprotected.

10. Code churn perspective. Analyzes git history to identify files and functions that change frequently. High-churn areas with high complexity are risk hotspots that deserve refactoring attention.

11. Dead code perspective. Uses the code graph to find functions, classes, and modules that are defined but never referenced anywhere in the codebase. Flags them for removal or review.

12. Performance perspective. Integrates with profiling tools or analyzes code patterns that are known performance anti-patterns (nested loops over large datasets, unnecessary allocations, blocking calls in async contexts).

### Phase 3: Agent Actions and Reports (Missions 10-12)

These features close the loop from analysis to action.

13. Audit report generation. After running one or more perspectives, Nala generates a comprehensive markdown audit report summarizing all findings, ranked by severity and actionability. The report includes specific file locations, code snippets, and recommended fixes.

14. Mission generation. From the audit report, Nala automatically generates a series of mission documents. Each mission is a self-contained task with a clear objective, context, acceptance criteria, and step-by-step implementation guidance. These missions are designed to be handed to a coding agent (like Claude Code) or tackled by a human developer.

15. Inline agent actions. The user can invoke agent actions directly from the TUI. Select a function, type "refactor this," and the agent applies changes in place. This is an opt-in feature that requires explicit user confirmation before any file is modified. The agent can also batch operations: "fix all complexity warnings in this module."

### Phase 4: Dashboard and Polish (Mission 13)

16. Optional web dashboard. A lightweight FastAPI server that spins up on localhost and renders the Neo4j code graph in a browser using D3.js or a similar visualization library. The user can explore the graph visually, click on nodes to see details, and filter by perspective. This is entirely optional and never required for the core workflow.

### Phase 5: Future Vision (Mission 14)

17. Custom model integration. The architecture supports plugging in fine-tuned models that are specifically trained on code analysis tasks. Eventually, Nala could run a chain of specialized local models (a complexity model, a security model, a style model) that collectively produce higher-quality analysis than any single foundation model.

18. MCP server support. Nala exposes its capabilities as an MCP server so other AI tools can use its indexing, analysis, and graph features.

19. Collaborative features. Shared sessions, team dashboards, and integration with GitHub/GitLab for PR-level analysis.

---

## Architecture Diagram (Plain English)

The system has four layers, bottom to top:

Layer 1 (Foundation): The file system. Your codebase on disk.

Layer 2 (Rust Core): Tree-sitter parser, rust-code-analysis metrics engine, content hash tracker, SQLite cache, LSP client, and the Ratatui TUI. This layer reads files, parses them, computes metrics, caches results, connects to language servers, and renders the terminal interface. Everything in this layer is Rust, compiled to a native binary.

Layer 3 (Python Orchestration): PyO3 bridge, Neo4j graph driver, LLM provider abstraction, perspective engine (complexity, dependency, coverage, churn, dead code, performance), session manager, report generator, and mission generator. This layer coordinates analysis, queries the graph, calls AI models, and produces structured output.

Layer 4 (Optional Web Dashboard): FastAPI server, D3.js graph visualization, perspective filter controls. This layer is entirely optional and runs on localhost when the user explicitly starts it.

The data flows like this: Files on disk are parsed by the Rust core into ASTs and metrics. Those results are pushed into both SQLite (for fast local queries) and Neo4j (for graph traversal). When the user requests an analysis, the Python orchestration layer queries the graph, applies perspective logic, optionally consults an LLM, and returns results to the Rust TUI for display. Sessions are saved to the `.nala/` directory. The web dashboard reads directly from Neo4j for visualization.

---

## Project Structure

```
nala/
  README.md
  LICENSE
  .github/
    workflows/
      ci.yml
  rust-core/                    # Rust workspace
    Cargo.toml                  # Workspace manifest
    nala-cli/                   # Binary crate (entry point)
      Cargo.toml
      src/
        main.rs                 # CLI entry, arg parsing, boot sequence
    nala-tui/                   # TUI crate
      Cargo.toml
      src/
        lib.rs
        app.rs                  # App state and event loop
        ui/
          mod.rs
          layout.rs             # Main layout and panel management
          command_bar.rs         # Command input area
          file_panel.rs          # File tree side panel
          session_panel.rs       # Session summary side panel
          status_bar.rs          # Bottom status bar
          splash.rs              # Boot splash / ASCII art
    nala-indexer/               # Indexing and parsing crate
      Cargo.toml
      src/
        lib.rs
        scanner.rs              # File system scanner
        hasher.rs               # Content hash computation
        parser.rs               # Tree-sitter integration
        metrics.rs              # rust-code-analysis integration
        symbol_graph.rs         # Symbol extraction and graph building
        cache.rs                # SQLite cache layer
    nala-lsp/                   # LSP client crate
      Cargo.toml
      src/
        lib.rs
        client.rs               # LSP client management
        config.rs               # Server detection and configuration
    nala-bridge/                # PyO3 bridge crate
      Cargo.toml
      src/
        lib.rs                  # Python module exposure via PyO3
  python-orchestrator/          # Python package
    pyproject.toml
    nala_orchestrator/
      __init__.py
      config.py                 # Configuration management
      graph/
        __init__.py
        connection.py           # Neo4j connection management
        schema.py               # Graph schema definitions
        queries.py              # Common Cypher queries
        builder.py              # Graph population from Rust data
      perspectives/
        __init__.py
        base.py                 # Base perspective class
        complexity.py           # Complexity analysis
        dependency.py           # Dependency analysis
        coverage.py             # Test coverage analysis
        churn.py                # Code churn analysis
        dead_code.py            # Dead code detection
        performance.py          # Performance analysis
      llm/
        __init__.py
        provider.py             # LLM provider abstraction
        anthropic_provider.py   # Claude integration
        openai_provider.py      # OpenAI integration
        ollama_provider.py      # Local model integration
      sessions/
        __init__.py
        manager.py              # Session lifecycle management
        report.py               # Markdown report generation
        missions.py             # Mission document generation
      agents/
        __init__.py
        orchestrator.py         # Agent task orchestration
        actions.py              # Inline agent actions
  dashboard/                    # Optional web dashboard
    requirements.txt
    server.py                   # FastAPI server
    static/
      index.html
      graph.js                  # D3.js graph visualization
  docs/
    ARCHITECTURE.md             # System architecture deep dive
    DATA_FLOW.md                # Data flow and integration patterns
    EXTENSION_GUIDE.md          # Extension points and plugin system
  tests/
    rust/                       # Rust integration tests
    python/                     # Python unit and integration tests
```

---

## Mission Index

The build is organized into 19 missions. Each mission is a self-contained unit of work with clear objectives, context, acceptance criteria, and implementation steps. Missions are designed to be executed sequentially, though some can be parallelized.

### Build Missions (01-14)

- Mission 01: Project Setup and Scaffolding
- Mission 02: File Scanner and Content Hasher
- Mission 03: Tree-sitter Parser and Metrics Engine
- Mission 04: TUI Shell and Boot Experience
- Mission 05: LSP Client Integration
- Mission 06: PyO3 Bridge and Python Scaffold
- Mission 07: Neo4j Code Graph and Symbol Population
- Mission 08: Pre-Analysis Chunking and Interactive Selection
- Mission 09: Analysis Perspectives Engine
- Mission 10: Session Management and Report Generation
- Mission 11: Mission Document Auto-Generation
- Mission 12: LLM Provider Integration
- Mission 13: Inline Agent Actions
- Mission 14: Optional Web Dashboard

### Quality Missions (15-16)

- Mission 15: Review, Polish, and Harden
- Mission 16: What's Next (Future Vision and Roadmap)

### Architecture Documentation Missions (17-19)

- Mission 17: System Architecture Deep Dive
- Mission 18: Data Flow and Integration Patterns
- Mission 19: Extension Points and Plugin System

---

## Success Criteria

Nala is successful when a developer can:

1. Type `nala` in a terminal and be inside a polished, responsive coding environment within 2 seconds.
2. Index a 100,000-line codebase in under 30 seconds on first run, and under 2 seconds on subsequent runs (incremental).
3. Navigate to any function definition in under 100ms.
4. Run a multi-perspective analysis and receive a structured markdown report within 60 seconds.
5. Generate actionable mission documents from the analysis that can be handed to Claude Code or another coding agent.
6. Feel like the tool was built by someone who genuinely cares about developer experience, not by someone who shipped the minimum viable product and moved on.

---

## Naming Note

"Nala" is a working name. It may change before public release. All references to "Nala" throughout the codebase should use a constant or configuration value so renaming is a single-line change.