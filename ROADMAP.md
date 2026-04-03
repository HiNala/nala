# Nala Roadmap

This document captures the planned evolution of Nala: a terminal-first, AI-powered coding environment. Items are organized by time horizon and priority. Each entry includes a brief description, estimated effort, and dependencies.

---

## Near-Term (Next 3 Months)

### 1. Additional Language Support
Expand Tree-sitter grammars and symbol extractors to cover Java, C/C++, Ruby, PHP, Kotlin, Swift, and C#. Each language is a small, scoped addition to `nala-indexer`: add the grammar crate, implement `LanguageExtractor`, register the file extension mapping, and configure the default LSP server.

**Effort**: Small per language. **Depends on**: Mission 03 (parser complete).

### 2. MCP Server Mode
Expose Nala's indexing, graph, and perspective capabilities as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server. This lets Claude Code, Cursor, and other MCP-aware tools use Nala as a backend for deep codebase understanding without launching the TUI.

**Effort**: Medium. **Depends on**: Mission 07 (graph), Mission 09 (perspectives).

### 3. Git Integration
Deeper git integration beyond churn analysis: commit-level diffs, branch comparisons, `git blame` annotation, and queries like "What changed between v1.0 and v2.0 and what is the risk?" Surface this data in the graph and in perspectives.

**Effort**: Medium. **Depends on**: Mission 07 (graph).

### 4. Configuration UI ✅
The `/settings` command provides a complete configuration interface for API keys, model preferences, task-type routing, autonomy levels, and git behavior — all persisted to `.nala/settings.toml`. Includes a `/settings setup` wizard for first-run configuration and `/settings set` for inline changes. Completed in Phase 7 (P7-03).

**Status**: Done.

### 5. Plugin System
Allow users to drop custom Python perspective scripts into `~/.nala/perspectives/` or the project's `.nala/perspectives/`. Nala discovers and loads them automatically on startup, making them available alongside built-in perspectives in the `/analyze` menu.

**Effort**: Small. **Depends on**: Mission 09 (perspectives base class).

---

## Medium-Term (3–6 Months)

### 6. Custom Model Fine-Tuning Pipeline
Build a pipeline for fine-tuning smaller models (7B–13B parameter) on code analysis tasks using Nala's own session data as training signal. Target models that excel at specific perspectives: complexity explanation, refactoring suggestions, security analysis. Run them locally via Ollama, zero API cost.

**Effort**: Large. **Depends on**: Mission 12 (LLM abstraction), large session corpus.

### 7. Multi-Model Chains ✅
The model registry, intelligent task-type routing, and mission-driven orchestration enable automatic multi-model workflows. Different models handle planning, coding, research, design, and review tasks based on their strengths. The orchestrator routes each mission to the optimal model. Completed in Phase 7 (P7-01, P7-02).

**Status**: Done (core infrastructure). Future: per-perspective model chains.

### 8. Collaborative Sessions
Share session reports with teammates via a configurable storage backend (local NFS, S3, or Nala Cloud). Support session comparison: "What improved since the last analysis?" Track finding resolution across the team.

**Effort**: Large. **Depends on**: Mission 10 (session persistence).

### 9. CI/CD Integration
Run Nala headless as part of a CI pipeline. Fail the build when new code introduces findings above a configured severity threshold. Post analysis summaries as PR comments via GitHub Actions or GitLab CI. Provide a `nala check` subcommand for this mode.

**Effort**: Medium. **Depends on**: Mission 09 (perspectives), Mission 10 (sessions).

### 10. IDE Extensions
Lightweight VS Code, NeoVim, and JetBrains extensions that connect to a running Nala instance for inline analysis results, symbol definitions from the graph, and quick access to session findings — without leaving the editor.

**Effort**: Large. **Depends on**: MCP server (item 2 above).

---

## Long-Term (6–12 Months)

### 11. Self-Healing Codebase
The ultimate vision. Nala continuously monitors the codebase for regressions (complexity creep, new security findings, test coverage drops), generates targeted missions when thresholds are breached, and — with explicit user permission — applies fixes automatically via agent actions. The developer shifts from writing fixes to reviewing them.

**Effort**: Very Large. **Depends on**: Mission 13 (agent actions), Mission 09 (perspectives), CI integration.

### 12. Cross-Repository Analysis
Analyze a fleet of repositories as a unified system. Understand inter-service dependencies, API contract drift, and which services are the most fragile blast radius for a given change. Essential for large microservice deployments.

**Effort**: Very Large. **Depends on**: Mission 07 (graph), Neo4j multi-graph support.

### 13. Architectural Pattern Recognition
Teach Nala to recognize common architectural patterns (MVC, hexagonal, event-driven, CQRS) by training on labeled codebases. Evaluate whether a codebase follows its own declared patterns consistently and surface drift as findings.

**Effort**: Research-heavy. **Depends on**: Mission 07 (graph), LLM fine-tuning.

### 14. Living Codebase Documentation
Automatically generate and maintain human-readable documentation from the code graph. As the code changes, the documentation updates. Output formats: Markdown, HTML, and MkDocs sites. Never manually write a README for an internal library again.

**Effort**: Large. **Depends on**: Mission 07 (graph), Mission 12 (LLM).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up the development environment and submit changes. Roadmap items without an assigned owner are open for contribution — open an issue to claim one.
