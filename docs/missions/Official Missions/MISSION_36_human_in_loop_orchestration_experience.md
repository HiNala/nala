# Mission 36: Human-In-The-Loop Orchestration Experience

## Objective

Design the full user experience for the interpreter terminal, `/agent` orchestrator, and spawned workers so the whole system feels understandable, controllable, and professional.

This mission is about the product behavior that ties all the previous technical work together.

## Why This Matters

The hardest part of autonomous coding products is not just making the agent capable. It is making the user feel they know:

- what is happening
- why it is happening
- what choices they have
- when to intervene
- how to resume control

That is the experience you described: the main terminal stays smart and calm, the orchestrator does heavy lifting when invoked, workers can branch out when useful, and the human always has meaningful options for how autonomous the system should be.

## External Research Context

Several current products highlight important UX patterns:

- Claude Code and Cursor both emphasize planning before execution and letting the user approve or redirect the work: [Claude Code](https://www.anthropic.com/claude-code/), [Cursor long-running agents](https://www.cursor.com/blog/long-running-agents)
- Windsurf adds useful UX ideas like queued messages, checkpoints, reverts, and real-time awareness of user actions: [Cascade overview](https://docs.windsurf.com/windsurf/cascade/cascade)
- Codex's task-thread model, integrated terminal, and worktree modes show how much value comes from making active work visible and bounded: [Codex app features](https://developers.openai.com/codex/app/features/)
- OpenCode's parent-child session model and agent switching reinforce that users need a clean way to move between summary view and specialist work: [OpenCode agents](https://opencode.ai/docs/agents)

## UX Model

### Main Interpreter terminal

This is where the user:

- asks questions
- starts `/agent`
- receives summaries
- sees approvals and next-step options
- decides between manual and autonomous flow

The interpreter should never dump raw internal complexity on the user unless they ask for it.

### Orchestrator experience

When `/agent` is active, the user should see:

- current objective
- current phase
- worker count and health
- pending approvals
- next recommended action

### Worker experience

Workers can be manual-inspection surfaces, but by default they should not demand attention. Their detailed work should be optional to inspect.

## Required User Choices

At every important step, the interpreter should offer clear choices such as:

- `continue automatically`
- `review the plan`
- `narrow the scope`
- `open worker 2`
- `run verification now`
- `pause and resume later`
- `cancel safely`

This is the heart of the human-in-the-loop design.

## Implementation Steps

### Step 1: Define standard summary message formats

The interpreter should use concise, repeatable message shapes for:

- plan ready
- approval required
- workers spawned
- worker blocked
- verification complete
- final summary

### Step 2: Add explicit autonomy controls

Support commands or UI actions for:

- `manual`
- `guided`
- `autonomous until blocked`

The user must always know which mode is active.

### Step 3: Add pause, resume, and checkpoint behavior

Longer runs should support:

- pause
- resume
- checkpoint creation
- revert to checkpoint when appropriate

### Step 4: Add takeover and return flow

When the user attaches to a worker:

- the UI should clearly indicate they are in a child session
- they should be able to send manual instructions
- the orchestrator should stay aware of this intervention

When they return:

- the interpreter should summarize what changed while they were inside the worker

### Step 5: Define notification and interruption strategy

The interpreter should decide when to interrupt the user versus when to keep quietly updating status.

Examples:

- interrupt for approval or safety issues
- quietly summarize progress milestones
- interrupt if a worker is blocked on a missing credential or tool

## Files To Change

- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/ui/layout.rs`
- `rust-core/nala-tui/src/ui/status_bar.rs`
- `rust-core/nala-tui/src/ui/agent_panel.rs`
- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/state.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `README.md`
- `docs/DATA_FLOW.md`

## Acceptance Criteria

- [ ] The interpreter terminal remains readable and useful while the orchestrator and workers operate
- [ ] The user always knows the current objective, phase, and autonomy level
- [ ] Important decisions are presented as explicit choices
- [ ] Attach/takeover and return flows are coherent
- [ ] Pause, resume, and checkpoint behavior are defined and implemented
- [ ] The experience feels like one system, not several disconnected features

## Estimated Complexity

High. This mission is mostly UX and orchestration design, but it determines whether the whole agent system feels trustworthy in daily use.
