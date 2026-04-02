# Mission 35: Web Search And Live Research Grounding

## Objective

Give `/agent` the ability to perform bounded, attributable web research so it can gather live technical context when the task requires it.

This mission covers the roadmap need for richer live context and the user experience requirement that the main terminal can explain what outside information the system used and why.

## Why This Matters

Many real tasks need current knowledge that is not in the local repo:

- package or framework docs
- API changes
- deployment instructions
- browser compatibility notes
- language server setup
- third-party service docs

Without live research, Nala either guesses or forces the user to leave the tool. With live research, `/agent` can stay useful on modern coding tasks, but only if that research is explicit, scoped, and inspectable.

## External Research Context

The major tools now treat web search as a first-class part of the coding workflow:

- Windsurf exposes web search directly inside Cascade for referenced suggestions: [Cascade overview](https://docs.windsurf.com/windsurf/cascade/cascade)
- OpenClaw treats web search and fetch as standard tools in the same orchestration system as file edits and shell commands: [OpenClaw tools and plugins](https://docs.openclaw.ai/tools)
- Codex supports web search as part of its coding environment, with explicit sandbox and search configuration: [Codex app features](https://developers.openai.com/codex/app/features/)
- Claude Code surfaces browser, terminal, and multi-surface workflow patterns that reinforce the value of grounded external context instead of pure hallucinated advice: [Claude Code](https://www.anthropic.com/claude-code/)

## Principles

### Principle 1: Research must be visible

When `/agent` uses the web, the user should see:

- what question triggered web research
- which sources were consulted
- what key facts were extracted
- what remains uncertain

### Principle 2: Research must be attributable

The system should preserve links and source labels in the session artifacts so a user can audit where important claims came from.

### Principle 3: Research must be bounded

Web research should not become an excuse for unlimited browsing.

Use:

- query budgets
- source count limits
- trusted-source bias when appropriate

## Implementation Steps

### Step 1: Add a research service

Create a service layer such as:

- `python-orchestrator/nala_orchestrator/research/service.py`
- `python-orchestrator/nala_orchestrator/research/models.py`
- `python-orchestrator/nala_orchestrator/research/cache.py`

This should manage:

- query requests
- fetched pages
- summarized facts
- citations

### Step 2: Add `/agent research` and implicit research hooks

Support:

- `/agent research <question>` for explicit user-invoked research
- automatic research during planning when the orchestrator detects a live-knowledge gap

Examples:

- missing framework syntax knowledge
- current package version changes
- tool installation docs
- deployment or platform behavior

### Step 3: Add research summaries to the interpreter

The main terminal should report short summaries like:

- "researched latest Next.js routing docs"
- "found 3 relevant Rust worktree references"
- "current package docs conflict with local assumptions"

### Step 4: Persist cited research artifacts

Store research notes under `.nala/agent/research/` so later runs can reuse relevant findings or at least expose them in handoffs and summaries.

## Files To Change

- `python-orchestrator/nala_orchestrator/research/service.py`
- `python-orchestrator/nala_orchestrator/research/models.py`
- `python-orchestrator/nala_orchestrator/research/cache.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `README.md`

## Acceptance Criteria

- [ ] `/agent` can run explicit web research with cited outputs
- [ ] The orchestrator can invoke live research during planning when needed
- [ ] The main terminal shows concise summaries of what was researched and why
- [ ] Research artifacts are persisted with links and extracted facts
- [ ] The user can distinguish repo-local facts from web-derived facts
- [ ] Research is budgeted and bounded

## Estimated Complexity

Medium to High. The mechanics are manageable, but the UX and trust model have to be carefully designed.
