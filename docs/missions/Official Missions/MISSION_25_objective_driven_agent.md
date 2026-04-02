# Mission 25: Objective-Driven Coding Agent

## Direction

Nala's strategic position is not "another chat-in-terminal tool." It is: **the most capable objective-driven coding agent for real repos.**

The existing foundation — fast indexing, LSP, perspectives, sessions, action previews, multi-agent hooks, context compression, handoff documents, and knowledge base — provides an unusually strong starting point. This mission turns those primitives into a tighter, safer, more intelligent agent loop than Claude Code, OpenCode, or Codex currently offer.

## North Star

A good Nala session should feel like this:

1. User gives an objective.
2. Nala scopes the repo automatically.
3. Nala proposes a plan with risks and affected files.
4. Nala makes changes in safe batches.
5. Nala runs the right checks.
6. Nala explains what changed, what passed, what still worries it, and what to do next.

## Four Differentiators

| Advantage | Description |
|-----------|-------------|
| **Persistent repo intelligence** | Nala remembers the codebase across sessions instead of rediscovering it every time. |
| **Proactive analysis** | Nala finds work worth doing before the user asks. |
| **Graph-aware action** | Nala estimates blast radius and dependency risk before editing. |
| **Safe completion loops** | Nala doesn't stop at "here's a patch" — it plans, edits, verifies, reviews, and summarizes. |

---

## Phase 6A: Proactive Intelligence (This Mission)

### 6A.1 — Proactive Startup

**Goal:** On launch, Nala immediately tells the user what it knows.

After indexing completes, automatically detect and display:
- Project type (Rust, Python, Node, Go, mixed) and likely entry points
- Current git branch, uncommitted changes count, ahead/behind status
- Risky hotspots from index (largest files, highest complexity)
- Open/incomplete sessions from previous runs
- 3–5 suggested next actions based on repo state

**Files changed:**
- `python-orchestrator/nala_orchestrator/cli.py` — add `startup_intelligence` IPC message after `ready`
- `python-orchestrator/nala_orchestrator/startup.py` — new module: repo detection, git status, suggestions
- `rust-core/nala-tui/src/python_bridge.rs` — handle `startup_intelligence` response
- `rust-core/nala-tui/src/app.rs` — new `BackgroundEvent::StartupIntelligence` variant
- `rust-core/nala-tui/src/ui/splash.rs` — render startup insights instead of static tips

**Acceptance criteria:**
- [ ] On boot, user sees project type, git branch, and file/symbol counts
- [ ] 3–5 contextual suggestions appear (e.g., "run /analyze", "review 3 uncommitted changes")
- [ ] Startup adds < 500ms to boot time
- [ ] Works with no git repo (graceful degradation)

### 6A.2 — Git Awareness

**Goal:** The agent understands the current diff, branch, and recent history.

Add commands:
- `/diff` — show current uncommitted changes summary
- `/branch` — show branch info, ahead/behind, recent commits
- `/status` — combined git status overview

**Files changed:**
- `python-orchestrator/nala_orchestrator/git_ops.py` — new module: safe git operations
- `python-orchestrator/nala_orchestrator/cli.py` — handle `git_diff`, `git_branch`, `git_status` IPC types
- `rust-core/nala-tui/src/commands.rs` — add `/diff`, `/branch`, `/status` slash commands
- `rust-core/nala-tui/src/python_bridge.rs` — add `GitDiff`, `GitBranch`, `GitStatus` bridge requests

**Acceptance criteria:**
- [ ] `/diff` shows a readable summary of uncommitted changes
- [ ] `/branch` shows current branch, tracking info, recent commits
- [ ] `/status` shows combined overview
- [ ] Works gracefully when not in a git repo

### 6A.3 — Task Ledger

**Goal:** Every agent run creates structured task objects for resumability and handoff.

Add `/task` command and task model:
- `/task <objective>` — create a new task with goal, auto-scoped files, constraints
- `/task status` — show current task state
- `/task list` — list tasks in current session
- `/task done` — mark current task complete with summary

Task objects contain: `objective`, `constraints`, `files_in_scope`, `plan`, `status`, `blocked_on`, `tests_run`, `artifacts`, `created_at`, `completed_at`.

**Files changed:**
- `python-orchestrator/nala_orchestrator/tasks/ledger.py` — new: `Task` model, `TaskLedger` manager
- `python-orchestrator/nala_orchestrator/tasks/__init__.py` — exports
- `python-orchestrator/nala_orchestrator/cli.py` — handle `task_*` IPC types
- `rust-core/nala-tui/src/commands.rs` — add `/task` slash command
- `rust-core/nala-tui/src/python_bridge.rs` — add task bridge requests

**Acceptance criteria:**
- [ ] `/task "fix auth bug"` creates a task with auto-detected scope
- [ ] Task state persists across the session
- [ ] `/task status` shows objective, plan, files, progress
- [ ] Tasks are included in handoff documents automatically

### 6A.4 — Improved Action Pipeline

**Goal:** Replace bare "query with actions" with plan → patch → verify → review.

When `/act` is used:
1. Agent first proposes a **plan**: which files to change, what the intended outcome is, and risks
2. User confirms the plan (or requests modifications)
3. Agent generates patches in safe batches
4. After applying, agent suggests verification commands
5. Agent summarizes what changed and what to check

**Files changed:**
- `python-orchestrator/nala_orchestrator/agents/orchestrator.py` — add `plan_then_act` method
- `python-orchestrator/nala_orchestrator/agents/action_executor.py` — add batch apply + rollback
- `python-orchestrator/nala_orchestrator/cli.py` — handle `plan_proposal` IPC type
- `rust-core/nala-tui/src/app.rs` — add `PlanProposal` background event
- `rust-core/nala-tui/src/commands.rs` — upgrade `/act` flow

**Acceptance criteria:**
- [ ] `/act` first shows a plan with files, changes, and risks
- [ ] User confirms before any edits happen
- [ ] After edits, verification commands are suggested
- [ ] Rollback is possible with `/undo` or reject

---

## Phase 6B: Reliability & Safety (Next Sprint)

### 6B.1 — Repo-Aware Command Recipes
Detect project type → map to correct build/test/lint commands.

### 6B.2 — Verification-First Edits
After agent edits, auto-run targeted tests/linters and report results.

### 6B.3 — Scope Controls
`/scope only-changed`, `/scope auth/`, `/scope exclude tests/` for surgical agent focus.

### 6B.4 — Action Safety Hardening
Every action records: intended outcome, affected files, reversible patch, validation commands, rollback path.

---

## Phase 6C: Deep Intelligence (60–90 Days)

### 6C.1 — Graph-Aware Planning
Before editing, analyze blast radius using the code graph: imports, references, likely test locations.

### 6C.2 — Proactive Triage
Auto-rank hotspots by `risk × complexity × churn × recency × centrality`, suggest missions.

### 6C.3 — Smart Context Engine
Auto-select files, symbols, diffs, diagnostics, and prior context based on the current task.

### 6C.4 — Session Memory Intelligence
Store durable learnings: architecture notes, conventions, repo commands, known flaky tests.

### 6C.5 — Project Brief Artifact
Maintain a machine-readable project briefing that refreshes over time.

---

## Phase 6D: Multi-Agent & Platform (90+ Days)

### 6D.1 — Named Agent Roles
Scout, Planner, Implementer, Verifier, Reviewer — each with narrow responsibilities.

### 6D.2 — Plugin System
Custom perspectives, validators, risk rules, repo recipes, task templates.

### 6D.3 — MCP/Server Mode
Expose Nala as a backend service for editors and other agents.

### 6D.4 — Mixed Autonomy Levels
"Plan only," "propose patches," "auto-apply safe," "full autonomous loop until blocked."

---

## Anti-Patterns to Avoid

- Don't become a generic shell wrapper around an LLM.
- Don't add slash commands without a coherent work loop.
- Don't over-index on multi-agent before single-agent reliability is excellent.
- Don't make the user micromanage context when indexing and sessions exist.
- Don't chase GUI polish before the agent loop itself is clearly better.

## Build Priority (This Session)

1. Proactive startup intelligence
2. Git awareness commands
3. Task ledger foundation
4. Action pipeline upgrade

Each item is committed and pushed as a verified working version.
