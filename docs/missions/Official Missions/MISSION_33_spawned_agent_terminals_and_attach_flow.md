# Mission 33: Spawned Agent Terminals And Attach Flow

## Objective

Allow `/agent` to spawn additional agent terminals for worker sessions, while keeping the main Nala terminal as the interpreter and summary surface.

Users must be able to:

- let the orchestrator spawn worker terminals automatically
- see what each worker is doing at a high level from the main terminal
- manually attach to a worker if they want to inspect or steer it
- return to the main terminal without losing context

## Why This Matters

Your desired UX is not just "parallel agents." It is "parallel agents with visible, controllable terminals." That is a powerful distinction because it preserves trust and agency:

- the user can stay hands-off and just read summaries
- or they can dive into a worker's context if they want

This is one of the biggest practical gaps between a nice demo and a truly usable autonomous coding product.

## External Research Context

Several products point in this direction:

- OpenCode supports parent and child sessions and explicit navigation between them, which is close to the attach/inspect model you want: [OpenCode agents](https://opencode.ai/docs/agents)
- OpenClaw's session tools and `sessions_spawn` model show a strong pattern for isolated spawned sessions with controlled visibility and messaging: [OpenClaw session tools](https://docs.openclaw.ai/concepts/session-tool)
- Codex's app treats each task thread as a bounded environment with its own terminal, making parallel work easier to inspect: [Codex app features](https://developers.openai.com/codex/app/features/)
- Cursor emphasizes user takeover and continuing work after planning and autonomous execution have already begun: [Cursor long-running agents](https://www.cursor.com/blog/long-running-agents)

## UX Goal

From the user's point of view:

1. They type `/agent <objective>`
2. The orchestrator creates a plan
3. If parallel work is useful, the orchestrator offers to spawn workers
4. The main terminal shows worker summaries
5. The user can run a command like `/agent workers` or `/agent attach <id>` to inspect a worker
6. They can return to the main interpreter view at any time

## Required Concepts

### Worker terminal metadata

Each worker needs:

- `worker_id`
- `label`
- `role`
- `objective`
- `scope`
- `status`
- `started_at`
- `terminal_ref`
- `parent_run_id`

### Attach model

The system should support:

- `list workers`
- `attach to worker`
- `detach back to interpreter`
- `send message to worker`
- `kill/cancel worker`

### Output discipline

Workers should stream detailed logs to their own terminal session, while the interpreter receives compressed summaries.

## Implementation Steps

### Step 1: Add worker terminal/session registry

Create a registry module to track active spawned workers and their terminal/session handles.

Suggested modules:

- `python-orchestrator/nala_orchestrator/agent_runtime/workers.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/registry.py`

### Step 2: Expose worker commands in the TUI

Add commands such as:

- `/agent workers`
- `/agent attach <worker-id>`
- `/agent message <worker-id> <text>`
- `/agent cancel-worker <worker-id>`

These should operate on the current parent `/agent` run.

### Step 3: Define terminal spawning strategy

The implementation may use one of two approaches:

- internal pseudo-terminals rendered inside the TUI, or
- actual external terminal sessions managed by Nala

For the first implementation, prefer the simpler, more reliable option for the current platform targets.

### Step 4: Add attach/detach UX

When attached to a worker, the UI must make it obvious that the user is no longer in the interpreter view.

The user should always have an easy way back, such as:

- `Esc`
- `/agent detach`
- a visible status bar indicator

## Files To Change

- `python-orchestrator/nala_orchestrator/agent_runtime/workers.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/registry.py`
- `python-orchestrator/nala_orchestrator/multi_agent/spawner.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/ui/layout.rs`
- `rust-core/nala-tui/src/ui/status_bar.rs`

## Acceptance Criteria

- [ ] The orchestrator can spawn up to 3 worker terminals or terminal-like sessions
- [ ] The main terminal shows concise summaries for each worker
- [ ] The user can list, attach to, message, and cancel workers
- [ ] The user can always return to the main interpreter cleanly
- [ ] Worker logs do not flood the main terminal
- [ ] Parent/child session identity remains visible and consistent

## Estimated Complexity

High. Terminal orchestration and attach/takeover semantics are product-defining and platform-sensitive.
