# Mission 28: Agent Control Plane And Central Brain Runtime

## Objective

Build a single control plane for `/agent` so Nala's deeper workflow is powered by one coherent runtime instead of several loosely connected features.

This is the mission that turns the current collection of capabilities into the "central brain" you described: one optional agent runtime that can see the indexed codebase, graph data, git state, task ledger, session memory, and verification pathways, then orchestrate them as one bounded workflow.

## Why This Matters

Right now Nala already has most of the raw ingredients:

- startup intelligence in `python-orchestrator/nala_orchestrator/startup.py`
- task persistence in `python-orchestrator/nala_orchestrator/tasks/ledger.py`
- multi-agent orchestration in `python-orchestrator/nala_orchestrator/multi_agent/`
- action extraction and execution in `python-orchestrator/nala_orchestrator/agents/`
- git summaries in `python-orchestrator/nala_orchestrator/git_ops.py`
- an IPC bridge in `python-orchestrator/nala_orchestrator/cli.py`

But the user-facing workflow still feels fragmented because there is no single runtime object that owns the active agent session and its lifecycle.

## External Research Context

The strongest agent systems all have some form of central control plane:

- OpenClaw explicitly separates tools, skills, and plugins, and treats tool use as part of a managed agent runtime instead of prompt-only behavior: [OpenClaw tools and plugins](https://docs.openclaw.ai/tools)
- OpenClaw's architectural descriptions also emphasize a central gateway coordinating sessions, memory, tools, and agents: [OpenClaw architecture search context](https://openclaw.cc/en/concepts/architecture)
- OpenAI's Codex describes long-horizon work as a repeated loop with durable project state and structured progress, not a stateless sequence of prompts: [Run long horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)
- Cursor's long-running agents rely on a harness that keeps plans, progress, and follow-through coherent across extended runs: [Cursor long-running agents](https://www.cursor.com/blog/long-running-agents)

Nala needs the same type of control plane, but grounded in its own strengths: local graph intelligence, session history, and terminal-first UX.

## Architecture Goal

Introduce an `AgentRuntime` or `AgentController` as the single owner of an active `/agent` run.

That runtime should manage:

- the user objective
- current phase
- repo scope
- active task ledger entry
- plan
- approval state
- team/worker execution state
- verification results
- summary artifacts

## Runtime Model

Create an explicit state machine for an agent run:

- `idle`
- `scoping`
- `planning`
- `awaiting_approval`
- `executing`
- `verifying`
- `reviewing`
- `done`
- `blocked`
- `cancelled`

Every `/agent` session should have a durable run record with:

- `run_id`
- `objective`
- `phase`
- `scope`
- `plan`
- `risk_summary`
- `verification_commands`
- `verification_results`
- `current_task_id`
- `team_run_active`
- `artifacts`
- `created_at`
- `updated_at`

## Implementation Steps

### Step 1: Create the runtime module

Add a new package such as:

- `python-orchestrator/nala_orchestrator/agent_runtime/__init__.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/state.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/toolbox.py`

The manager should orchestrate existing subsystems instead of reimplementing them.

### Step 2: Define the agent run state model

In `state.py`, create dataclasses or typed models for:

- `AgentRun`
- `AgentPhase`
- `AgentPlan`
- `AgentReview`
- `AgentVerification`

Persist active run state inside `.nala/agent/` so it survives restarts and can be resumed.

### Step 3: Move `/brain` logic behind the runtime

Anything currently treated as "Brain Mode" should become `/agent` runtime behavior:

- hotspot triage
- task creation
- git review
- verification helpers
- team-run orchestration

The TUI should ask the runtime for agent status, not manually stitch together task and team summaries.

### Step 4: Add IPC request types

Extend `python-orchestrator/nala_orchestrator/cli.py` and `rust-core/nala-tui/src/python_bridge.rs` with a dedicated `/agent` request family, for example:

- `agent_start`
- `agent_status`
- `agent_plan`
- `agent_run`
- `agent_review`
- `agent_verify`
- `agent_hotspot`
- `agent_resume`
- `agent_cancel`

At the Rust layer, the `/agent` command handler should call these higher-level runtime requests instead of mixing together low-level bridge calls directly.

### Step 5: Integrate the existing task ledger

Connect `python-orchestrator/nala_orchestrator/tasks/ledger.py` to the new runtime so each active agent run automatically owns or references a current task.

If a task already exists, `/agent <objective>` should either:

- continue the existing task when the objective matches closely, or
- create a new run and task when the objective is materially different

### Step 6: Integrate the multi-agent engine as an internal tool

The `LeadAgent` in `python-orchestrator/nala_orchestrator/multi_agent/lead.py` should become an internal execution tool for the runtime, not the primary user-facing concept.

Users ask `/agent`, not `/team`.

## Files To Change

- `python-orchestrator/nala_orchestrator/agent_runtime/__init__.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/state.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/toolbox.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `python-orchestrator/nala_orchestrator/tasks/ledger.py`
- `python-orchestrator/nala_orchestrator/multi_agent/lead.py`
- `rust-core/nala-tui/src/python_bridge.rs`
- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/commands.rs`

## Acceptance Criteria

- [x] `/agent` is backed by a single runtime object in Python (`AgentManager`)
- [x] The active agent run has explicit phases and durable state (`AgentPhase` enum, `AgentRun` dataclass)
- [x] The runtime can start, report status, resume, and cancel a run
- [x] Task ledger integration is automatic rather than manual
- [x] Multi-agent execution is hidden behind the runtime instead of exposed as a separate primary workflow
- [x] Restarting Nala does not destroy the current agent run state (persists to `.nala/agent/current_run.json`)

## Estimated Complexity

High. This is the structural mission that makes the rest of the `/agent` experience possible.
