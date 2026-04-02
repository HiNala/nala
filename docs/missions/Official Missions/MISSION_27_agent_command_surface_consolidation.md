# Mission 27: `/agent` Command Surface Consolidation

## Objective

Refactor Nala's current command surface so the optional autonomous workflow is entered through a single, obvious entrypoint: `/agent`.

Today the app exposes overlapping commands for action mode, task tracking, git summaries, team orchestration, and Brain Mode. That makes the product harder to learn and harder to evolve. This mission establishes one coherent user-facing workflow so future coding agents can refactor the runtime and UI without guessing which command families are canonical.

## Why This Matters

The codebase already shows the drift:

- `rust-core/nala-tui/src/commands.rs` exposes `/act`, `/task`, `/team`, `/diff`, `/branch`, `/status`, and `/brain`
- `rust-core/nala-tui/src/app.rs` includes all of those in slash completion
- `README.md` advertises `/brain` as the optional deeper workflow
- `python-orchestrator/nala_orchestrator/cli.py` already has separate IPC pathways for actions, tasks, git, and team runs

This is exactly the point where many coding tools get messy: every new capability adds a new slash command instead of making the main workflow better. This mission fixes that before more agent features land.

## External Research Context

The current market is converging on fewer, stronger entrypoints instead of many scattered verbs:

- Anthropic positions Claude Code around a unified coding assistant that spans terminal, IDE, desktop, and web, rather than exposing separate product names for planning, editing, and execution: [Claude Code](https://www.anthropic.com/claude-code/)
- OpenAI's Codex emphasizes thread-based workflows with one task surface that owns planning, diffs, terminal usage, git review, and verification: [Codex app features](https://developers.openai.com/codex/app/features/)
- Windsurf's Cascade groups longer work into one assistant surface with modes, checkpoints, queued messages, and linter integration: [Cascade overview](https://docs.windsurf.com/windsurf/cascade/cascade)
- OpenCode separates internal agent roles, but still keeps the user-facing experience centered on a small set of primary agents and subagents instead of a sprawling command list: [OpenCode agents](https://opencode.ai/docs/agents)

Nala should follow the same principle while keeping its terminal-first identity.

## Target UX

After this mission, the canonical workflow should look like this:

- `/agent` — show help for the active agent run, or the current run status if one exists
- `/agent <objective>` — create or resume an objective-driven agent run
- `/agent plan [objective]` — create or refresh a plan without executing changes
- `/agent run` — execute the approved plan
- `/agent review` — review current diff, decisions, and pending approvals
- `/agent verify` — run verification and summarize results
- `/agent hotspot` — run quick hotspot triage and suggest high-value work
- `/agent status` — show current objective, phase, task progress, scope, git state, and blockers
- `/agent stop` — cancel the active run cleanly
- `/agent resume` — resume a paused or blocked run

## Commands To Deprecate Or Fold In

These should stop being first-class workflows and become aliases or internal plumbing:

- `/brain` and all `/brain ...` subcommands → replace with `/agent ...`
- `/act` → fold into `/agent <objective>` and `/agent review`
- `/task` → fold into `/agent status` and internal task ledger views
- `/team` → keep as an internal runtime primitive, not a primary user-facing command
- `/diff`, `/branch`, `/status` → fold into `/agent review` and `/agent status`

For one release, deprecated aliases may remain, but they must print a short migration hint like:

`/brain is deprecated. Use /agent instead.`

## Implementation Steps

### Step 1: Define the canonical command map

Update the command taxonomy in:

- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `README.md`
- `docs/DATA_FLOW.md`

Document which commands are:

- user-facing and stable
- transitional aliases
- internal-only runtime hooks

### Step 2: Add `/agent` dispatch in the TUI

Implement a dedicated `/agent` handler in `rust-core/nala-tui/src/commands.rs` that routes subcommands to the existing task, git, action, and team functions while the deeper runtime is still being refactored.

This mission does not need to finish the entire central-brain runtime. It needs to establish the public interface cleanly now.

### Step 3: Replace slash completion and help text

Update:

- `rust-core/nala-tui/src/app.rs` slash completion entries
- `rust-core/nala-tui/src/commands.rs` help text
- any prompt hints or startup suggestions in `python-orchestrator/nala_orchestrator/startup.py`

The visible command surface should bias toward:

- `/agent`
- `/analyze`
- `/scope`
- `/session`
- `/memory`
- `/context`
- `/dashboard`
- core navigation commands like `/def`, `/refs`, `/hover`

### Step 4: Keep aliases, but mark them deprecated

For `/brain`, `/act`, `/task`, `/team`, `/diff`, `/branch`, and `/status`:

- keep them temporarily working if practical
- print a clear migration message
- route them to the new `/agent` flow

This reduces breakage while making the preferred experience obvious.

### Step 5: Hide implementation details from users

The user should not need to think in terms of:

- action extraction
- team runs
- task ledger plumbing
- separate git summary commands

Those can still exist internally, but `/agent` should be the umbrella workflow that owns them.

## Files To Change

- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/python_bridge.rs`
- `python-orchestrator/nala_orchestrator/startup.py`
- `README.md`
- `docs/DATA_FLOW.md`
- `docs/missions/Official Missions/MISSION_26_brain_mode_optional_workflow.md`

## Acceptance Criteria

- [ ] `/agent` exists as the primary entrypoint for the optional autonomous workflow
- [ ] `/brain` is deprecated in help text and routed to `/agent`
- [ ] `/act`, `/task`, `/team`, `/diff`, `/branch`, and `/status` are either folded into `/agent` or explicitly marked transitional
- [ ] Slash completion and `/help` make `/agent` the obvious path
- [ ] The command surface is simpler after the change, not more complex
- [ ] README and flow docs match the new command model

## Estimated Complexity

Medium. The code changes are straightforward, but the design decision is high leverage because every later mission depends on this command surface being coherent.
