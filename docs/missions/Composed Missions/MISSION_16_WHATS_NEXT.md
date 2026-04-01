# Mission 16: What's Next

## Objective

Define the next phase of Nala's development with a concrete roadmap, prioritised backlog, and future vision.

## Near-Term (Next 3 Missions After Launch)

### Mission A: Full LSP Implementation
Complete the LSP client with real JSON-RPC transport. Connect `go_to_definition`, `find_references`, and `hover` to the TUI. This is what makes code navigation instant.

### Mission B: Complete Analysis Perspectives
Implement all 6 perspectives beyond the current complexity stub:
- **Dependency** — circular deps, tight coupling, fan-in/fan-out (requires Neo4j)
- **Dead code** — functions never called (requires call graph)
- **Churn** — git history analysis for hotspot identification
- **Coverage** — integrate with test coverage tools (tarpaulin for Rust, pytest-cov for Python)
- **Performance** — common anti-patterns (nested loops, blocking I/O in async)
- **Security** — OWASP top 10 patterns, hard-coded secrets, SQL injection

### Mission C: Full Inline Agent Actions
Complete Mission 13 — allow the agent to actually modify files with explicit user confirmation. The flow: select code → type instruction → see diff → confirm → apply.

## Medium-Term

### Multi-File Context
Today the agent gets project-level stats. Next: automatically include relevant file content in the context window based on semantic similarity to the query (using embeddings).

### Streaming Responses in TUI
Token-by-token streaming already has placeholders in `app.rs`. Wire it up via the PyO3 bridge for a ChatGPT-style typewriter effect.

### Persistent Chat History
Save conversation history per session so the user can resume where they left off. Store in `{session_dir}/chat.jsonl`.

### Git Integration
Read git history for code churn analysis. Show blame information. Create commit messages from agent actions.

## Long-Term Vision

### MCP Server
Expose Nala's capabilities (codebase index, complexity analysis, symbol graph) as an MCP server. Let other AI tools (Claude Code, Cursor, etc.) use Nala's deep codebase understanding.

### Custom Fine-Tuned Models
Train specialised small models on code analysis tasks. A complexity model. A security model. A style model. Run them locally for instant, privacy-preserving analysis.

### Collaborative Features
- Shared sessions via a lightweight sync server
- Team dashboards showing codebase health over time
- GitHub/GitLab integration: PR-level analysis before push

### Plugin System
A documented extension API so the community can add new languages, new perspectives, new LLM providers, and new visualisations without touching the core.

## Metrics to Track

| Metric | Current | Goal |
|--------|---------|------|
| Boot time | ~500ms | < 200ms |
| 100k-line index | < 30s | < 10s |
| Supported languages | 5 | 15+ |
| Active perspectives | 1 | 6 |
| GitHub stars | 0 | 500 |

## Community Priorities

Before public launch, prioritise:
1. Excellent documentation (the missions + ARCHITECTURE.md)
2. A 5-minute getting-started screencast
3. Easy install (single binary download)
4. Windows support (currently tested, needs CI)
5. A clear contribution guide

## The One Thing That Matters Most

Speed. Every decision — Rust core, Rayon parallelism, SQLite cache, incremental parsing — serves the goal of making Nala feel instant. If Nala ever starts feeling slow, that is a P0 bug. Speed is the product.
