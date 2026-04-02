# Mission 32: Interpreter, Orchestrator, And Worker Architecture

## Objective

Formalize Nala's terminal-native multi-agent architecture as three layers:

1. `Interpreter Layer` — the main terminal the user always interacts with
2. `Orchestrator Layer` — the `/agent` runtime that plans, delegates, tracks, and summarizes
3. `Worker Layer` — up to three spawned sub-agents that execute scoped tasks in parallel

This mission defines the runtime model so the product behaves coherently before more UI and execution features are added.

## Why This Matters

The workflow you want is more specific than "multi-agent" in general:

- the user keeps one primary terminal open for asking questions and reading summaries
- `/agent` starts a deeper orchestration flow when the user wants it
- the orchestrator can spawn a small bounded set of workers
- workers do real work in scoped contexts
- the main terminal remains the interpreter that tells the user what is happening and what choices they have

Without this architectural separation, Nala risks becoming a pile of concurrent chat surfaces with no clear authority model.

## External Research Context

This layered approach is consistent with where the best systems are going:

- Claude Code subagents run in separate context windows with distinct tool access and permissions, preserving the main conversation while delegating work: [Claude Code subagents](https://docs.claude.com/en/docs/claude-code/subagents)
- OpenCode distinguishes primary agents from subagents and gives users explicit navigation between parent and child sessions: [OpenCode agents](https://opencode.ai/docs/agents)
- OpenClaw provides session tools like `sessions_spawn`, `sessions_send`, and `sessions_history`, which is a strong model for bounded sub-agent orchestration instead of uncontrolled recursion: [OpenClaw session tools](https://docs.openclaw.ai/concepts/session-tool), [OpenClaw sub-agents](https://docs.openclaw.ai/tools/subagents)
- Cursor's long-running agent research suggests that planning, delegated execution, and synthesis work better when the system has a real harness rather than a single undifferentiated agent loop: [Cursor long-running agents](https://www.cursor.com/blog/long-running-agents)

## Architecture Rules

### Rule 1: The user always owns the Interpreter terminal

The primary Nala terminal is the stable home for:

- user input
- concise summaries
- decisions and approvals
- progress updates
- attach/takeover options

It should never become unreadable due to raw worker logs.

### Rule 2: `/agent` owns orchestration, not conversation

The orchestrator is a workflow manager, not just another chat thread. It must own:

- objective lifecycle
- plan generation
- task decomposition
- worker assignment
- progress synthesis
- final reporting

### Rule 3: Workers are bounded and specialized

For now, the orchestrator may spawn at most `3` workers total.

Workers should be explicitly typed, for example:

- `research`
- `implement`
- `verify`

Or:

- `explore`
- `edit`
- `review`

The important point is that the orchestrator decides their role and scope.

### Rule 4: Workers do not recurse infinitely

Worker agents must not spawn further child agents by default.

If deeper recursion is ever supported later, it should be behind explicit runtime limits and not enabled in the baseline design.

## Runtime Responsibilities

### Interpreter Layer

Lives primarily in:

- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/ui/layout.rs`

Responsibilities:

- route user messages and commands
- show summaries and approvals
- let the user open/close or attach to worker terminals
- remain the single reliable place for status

### Orchestrator Layer

Lives primarily in:

- `python-orchestrator/nala_orchestrator/agent_runtime/`
- `python-orchestrator/nala_orchestrator/multi_agent/lead.py`

Responsibilities:

- create plan
- spawn workers
- coordinate progress
- manage task graph
- manage approval gates
- summarize for interpreter

### Worker Layer

Lives primarily in:

- `python-orchestrator/nala_orchestrator/multi_agent/spawner.py`
- `python-orchestrator/nala_orchestrator/multi_agent/task_list.py`
- `python-orchestrator/nala_orchestrator/multi_agent/messages.py`

Responsibilities:

- perform one bounded task
- report progress and findings
- request clarification or escalation when blocked

## Implementation Steps

### Step 1: Define the three-layer runtime contract

Document and implement a typed contract for:

- interpreter-to-orchestrator requests
- orchestrator-to-interpreter summaries
- orchestrator-to-worker assignments
- worker-to-orchestrator result messages

### Step 2: Add worker role types and limits

Add explicit worker roles and enforce:

- max worker count = 3
- no recursive worker spawning
- each worker must have a named scope

### Step 3: Build message formats for summaries

The orchestrator should send compact structured updates to the main terminal like:

- "planning complete"
- "2 workers running"
- "worker 1 blocked on missing env var"
- "verification failed in worker 3"
- "approval needed for 4 files"

### Step 4: Persist interpreter-orchestrator-worker relationships

Store parent/child run metadata so sessions can be resumed and users can reattach to active workers later.

## Files To Change

- `python-orchestrator/nala_orchestrator/agent_runtime/state.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/multi_agent/lead.py`
- `python-orchestrator/nala_orchestrator/multi_agent/spawner.py`
- `python-orchestrator/nala_orchestrator/multi_agent/task_list.py`
- `python-orchestrator/nala_orchestrator/multi_agent/messages.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/commands.rs`

## Acceptance Criteria

- [ ] The architecture clearly separates interpreter, orchestrator, and worker responsibilities
- [ ] The main terminal remains the stable user-facing interpreter
- [ ] `/agent` owns planning and delegation
- [ ] Worker count is capped at 3
- [ ] Workers cannot recursively spawn more workers by default
- [ ] Parent/child relationships are persisted for later attach/resume flows

## Estimated Complexity

High. This is the conceptual backbone for the terminal-native orchestration UX.
