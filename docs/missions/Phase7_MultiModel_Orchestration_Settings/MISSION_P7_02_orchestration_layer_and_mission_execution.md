# Phase 7 Mission 02: Orchestration Layer And Mission-Driven Execution

## Objective

Build the orchestration layer that turns a user's high-level request into a structured plan of missions, routes each mission to the right model and worker, manages git safely, and loops execution until the objective is complete or the user stops it.

This is the "brain" that coordinates everything: the interpreter terminal tells it what the user wants, and it figures out how to get there using the model registry, worker agents, git worktrees, and verification loops.

## Why This Matters

The user workflow you are building is:

1. User opens HiNala on a repo or empty folder
2. User describes what they want (e.g., "build me a website for my APA-compliant AI scheduling system")
3. The interpreter terminal explains what will happen and offers choices: manual vs. autonomous
4. If the user chooses `/agent`, the orchestrator takes over:
   - researches the request (using a research-grade model)
   - creates a structured plan as mission `.md` files in a nested directory structure
   - presents the plan to the user for approval
   - executes missions sequentially or in parallel using worker agents
   - each worker uses the model best suited for its task type
   - git commits are handled automatically by the orchestrator
   - progress flows back to the interpreter terminal as concise summaries
   - the loop continues until all missions are complete
5. The user gives feedback and approvals along the way

This mission implements that orchestration backbone.

## Current State In Nala

The existing pieces are:

- `LeadAgent` in `multi_agent/lead.py` — basic wave-based task decomposition and parallel worker execution
- `TaskDecomposer` in `multi_agent/decomposer.py` — keyword-heuristic decomposition (does not use graph or LLM)
- `SharedTaskList` in `multi_agent/task_list.py` — SQLite task queue with dependency resolution
- `AgentSpawner` in `multi_agent/spawner.py` — creates `WorkerAgent` instances, max 3 concurrent
- `TaskLedger` in `tasks/ledger.py` — session-scoped task persistence
- `AgentOrchestrator` in `agents/orchestrator.py` — single-model query/action orchestration
- `agent_runtime/` — early runtime with state, manager, and toolbox stubs

What is missing is the glue that turns a high-level objective into LLM-generated mission files, routes work to models intelligently, manages git throughout, and loops until done.

## External Research Context

- Cursor's self-driving codebases research showed that a recursive planner-worker hierarchy outperforms self-coordination: planners create tasks, workers execute, no shared-file bottlenecks: [Cursor self-driving codebases](https://cursor.com/blog/self-driving-codebases)
- OpenAI emphasizes durable project memory in long-horizon runs: spec, plan, implementation runbook, and status docs that the agent revisits continuously: [Codex long-horizon tasks](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)
- OpenClaw's session tools allow spawning sub-agents with task labels, runtime limits, cleanup policies, and controlled nesting depth: [OpenClaw sub-agents](https://docs.openclaw.ai/tools/subagents)
- Dispatch-table routing is preferred over prompt-based model selection for reliability: [Multi-model routing best practices](https://dev.to/toji_openclaw_fd3ff67586a/orchestrating-10-ai-agents-patterns-that-actually-work-23bm)

## Architecture

### Orchestrator Responsibilities

The orchestrator must own:

1. **Objective intake** — receive the user's request from the interpreter
2. **Research phase** — use a research-grade model to gather context, understand requirements, identify tech stack decisions
3. **Mission generation** — produce structured `.md` mission files in `.nala/agent/missions/` organized by phase
4. **Plan presentation** — show the plan to the user with approval/edit/reject options
5. **Mission dispatch** — route each mission to a worker with the correct model and scope
6. **Sequential and parallel control** — respect mission dependencies and parallelize where safe
7. **Git management** — create branches, commit after verified milestones, manage worktrees for parallel workers
8. **Progress synthesis** — send concise summaries to the interpreter terminal
9. **Completion loop** — after each mission completes, check remaining work, re-plan if needed, continue until done
10. **User interaction routing** — when a worker or the orchestrator needs user input, surface it clearly in the interpreter

### Mission File Format

Generated mission files should follow a consistent structure:

```markdown
# Mission: [title]

## Objective
[1-2 sentences]

## Task Type
[plan | code | design | research | review | verify]

## Model Preference
[Recommended model tier or specific model]

## Dependencies
[List of mission IDs that must complete first, or "none"]

## Parallel Group
[Group ID for missions that can run simultaneously, or "sequential"]

## Scope
[Files and directories this mission should touch]

## Steps
1. [Concrete step]
2. [Concrete step]
...

## Verification
[How to confirm this mission is done correctly]

## Acceptance Criteria
- [ ] [Criterion]
- [ ] [Criterion]
```

### Execution Flow

```
User request
  → Interpreter presents options (manual / guided / autonomous)
  → /agent starts orchestrator
    → Research model gathers context
    → Planning model generates mission files
    → User approves plan
    → For each mission (respecting dependencies):
      → Router selects model
      → Orchestrator assigns to worker (or self for planning tasks)
      → Worker executes in scoped context (optionally in worktree)
      → Worker reports results
      → Orchestrator verifies (runs checks, reviews output)
      → Orchestrator commits to git if verified
      → Orchestrator updates interpreter with summary
    → When all missions complete:
      → Final synthesis and summary
      → Present to user with next-step suggestions
```

### Git Management

The orchestrator should:

- detect if the repo is a git repository
- create a feature branch for the agent run (e.g., `nala/agent-<run-id>`)
- commit verified milestones with descriptive messages
- use worktrees for parallel workers editing different file sets
- never force-push or rewrite history
- present the final branch diff to the user for merge/squash decision

## Implementation Steps

### Step 1: Build the orchestrator execution engine

Extend `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`:

- add `start_objective(objective: str, autonomy: str)` method
- add research phase using the model router's `research` task type
- add mission generation phase using the `plan` task type model

### Step 2: Build the mission file generator

Create `python-orchestrator/nala_orchestrator/agent_runtime/mission_writer.py`:

- accept a structured plan from the planning model
- write `.md` mission files to `.nala/agent/missions/<run-id>/`
- support both sequential and parallel mission grouping

### Step 3: Build the mission executor loop

Create `python-orchestrator/nala_orchestrator/agent_runtime/executor.py`:

- load mission files
- resolve dependency order
- dispatch to workers via the model router and spawner
- collect results
- verify each mission
- loop until all missions are complete or the user stops

### Step 4: Add git orchestration

Extend `python-orchestrator/nala_orchestrator/git_ops.py`:

- `create_agent_branch(run_id)`
- `commit_milestone(message, files)`
- `create_worktree_for_worker(worker_id)`
- `cleanup_worktree(worker_id)`
- `get_run_diff_summary()`

### Step 5: Add interpreter summary protocol

Define structured messages from orchestrator to interpreter:

- `phase_update` — "researching", "planning", "executing mission 3/7", "verifying"
- `approval_request` — "plan ready, approve?"
- `worker_update` — "worker 1: building docker config"
- `user_question` — "worker 2 needs: what database port?"
- `completion` — "all missions done, 23 files changed, branch ready for review"

### Step 6: Wire into `/agent` command

The `/agent` command (from Mission 27) should now route objectives to this orchestration engine.

## Files To Change

- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/executor.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/mission_writer.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/state.py`
- `python-orchestrator/nala_orchestrator/models/router.py`
- `python-orchestrator/nala_orchestrator/multi_agent/lead.py`
- `python-orchestrator/nala_orchestrator/multi_agent/spawner.py`
- `python-orchestrator/nala_orchestrator/git_ops.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/python_bridge.rs`

## Acceptance Criteria

- [ ] A high-level user objective produces structured mission `.md` files
- [ ] Mission files are organized by phase and dependency
- [ ] The orchestrator dispatches missions to workers with appropriate models
- [ ] Sequential and parallel execution are both supported
- [ ] Git branching and milestone commits happen automatically
- [ ] The interpreter terminal receives structured progress updates
- [ ] The execution loop continues until all missions pass verification or the user stops
- [ ] User questions from workers are surfaced in the interpreter terminal

## Estimated Complexity

Very High. This is the most complex single mission in the entire product because it connects the model layer, the worker layer, the git layer, and the user interaction layer into one execution engine.
