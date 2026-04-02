# Mission 31: Agent Skills, Scoped Memory, And Safe Autonomy

## Objective

Finish the first serious version of `/agent` by giving it durable project memory, scoped guidance, reusable skills, and safe execution boundaries.

This mission is what makes the central brain feel intelligent across sessions instead of merely capable inside one chat.

## Why This Matters

An autonomous coding workflow gets dramatically better when it can rely on:

- project-level briefings
- directory-specific rules
- reusable workflow skills
- explicit autonomy levels
- isolated execution when risk is high

Nala already has sessions, handoffs, knowledge memory, and `.nala` artifacts. This mission turns those into a practical operating system for `/agent`.

## External Research Context

The best product ideas here are now well established:

- OpenClaw separates tools, skills, and plugins so agents have reusable operating knowledge instead of oversized prompts: [OpenClaw tools and plugins](https://docs.openclaw.ai/tools)
- Windsurf's `AGENTS.md` model is a strong pattern for directory-scoped instructions that activate automatically: [Windsurf AGENTS.md](https://docs.windsurf.com/windsurf/cascade/agents-md)
- OpenCode makes agent roles, permissions, and subagents configurable at the project level: [OpenCode agents](https://opencode.ai/docs/agents)
- Codex exposes skills, worktrees, and isolated task modes because parallel or risky work needs stronger boundaries than a normal local thread: [Codex app features](https://developers.openai.com/codex/app/features/)

Nala should adopt those ideas in a way that fits its terminal-first, local-first architecture.

## Deliverables

### 1. Rename persistent Brain artifacts to Agent artifacts

Anything under `.nala/brain/` should be migrated to `.nala/agent/`.

That includes:

- `.nala/agent/project-brief.md`
- `.nala/agent/scopes/*.md`
- `.nala/agent/skills/*.md`
- `.nala/agent/runs/*.json`

### 2. Project brief

Maintain a durable project brief containing:

- architecture summary
- main entry points
- common build/test/lint commands
- dangerous areas
- repo conventions
- known flaky tests or environmental issues

This should be refreshable over time, not static.

### 3. Scoped guidance

Support directory-scoped instruction files, similar to `AGENTS.md`, so `/agent` automatically picks up local conventions when operating in a subsystem.

Examples:

- `.nala/agent/scopes/rust-core.md`
- `.nala/agent/scopes/python-orchestrator.md`
- `.nala/agent/scopes/dashboard.md`

### 4. Skills

Create a skill system for common agent workflows such as:

- `triage-hotspots`
- `review-current-diff`
- `refactor-safely`
- `repair-verification-failures`
- `prepare-shippable-summary`

Each skill should define:

- when to use it
- what tools or subsystems it may call
- what the output contract is

### 5. Autonomy levels

Add explicit agent modes such as:

- `observe` — investigate only
- `plan` — produce plan, no edits
- `patch` — propose or apply limited patches with approval
- `autonomous` — run plan/execute/verify until blocked

The active mode must always be visible in the TUI.

### 6. Optional worktree isolation

For riskier or longer `/agent` runs, support isolated execution using git worktrees so the user can keep their main branch clean while the agent experiments.

## Implementation Steps

### Step 1: Build the agent memory directory contract

Standardize a persistent directory layout under `.nala/agent/` and update any startup or runtime code that still writes under `.nala/brain/`.

### Step 2: Create a skill loader

Add a small skill registry such as:

- `python-orchestrator/nala_orchestrator/skills/registry.py`
- `python-orchestrator/nala_orchestrator/skills/models.py`

The runtime should be able to list, resolve, and invoke skills by name.

### Step 3: Load scoped guidance automatically

When the runtime scopes a task to a directory, it should load matching scope documents and include them in planning and execution context.

### Step 4: Add autonomy and isolation controls

Expose `/agent mode ...` and optional `/agent isolate` or equivalent runtime flags so the user can choose safety boundaries explicitly.

### Step 5: Persist reusable summaries

The project brief and scope files should be updated from:

- session summaries
- handoff artifacts
- repeated successful verification recipes
- recurring failure patterns

## Files To Change

- `python-orchestrator/nala_orchestrator/startup.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/state.py`
- `python-orchestrator/nala_orchestrator/skills/registry.py`
- `python-orchestrator/nala_orchestrator/skills/models.py`
- `python-orchestrator/nala_orchestrator/memory/knowledge.py`
- `python-orchestrator/nala_orchestrator/sessions/manager.py`
- `python-orchestrator/nala_orchestrator/git_ops.py`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `README.md`

## Acceptance Criteria

- [x] `.nala/brain/` has been migrated to `.nala/agent/` for the new workflow
- [x] `/agent` can load a durable project brief and directory-scoped guidance
- [x] Skills exist and are actually used by the runtime
- [x] The user can choose autonomy levels explicitly
- [ ] Riskier runs can opt into worktree isolation (deferred — requires git worktree infra)
- [x] Agent memory improves continuity across sessions without becoming opaque

## Estimated Complexity

High. This mission is less about flashy UX and more about making `/agent` reliable, reusable, and scalable over time.
