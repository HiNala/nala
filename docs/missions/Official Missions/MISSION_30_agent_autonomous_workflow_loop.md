# Mission 30: `/agent` Autonomous Workflow Loop

## Objective

Implement the real `/agent` loop: scope, plan, approval, execution, verification, review, and final summary.

This mission is where the central brain stops being a naming change and becomes a trustworthy coding workflow. The user gives an objective, Nala does the heavy lifting, but every important step stays visible and governable.

## Why This Matters

This is the core product behavior you want:

- boot HiNala on any folder or repo
- begin interacting normally
- run `/agent` with or without a starter prompt
- let Nala kick off a bounded autonomous workflow that uses the indexed codebase, graph, git state, sessions, and verification tools to move the work forward

Without this mission, `/agent` is only a shell around existing commands. With this mission, `/agent` becomes the actual central brain experience.

## External Research Context

This loop is where the industry is clearly converging:

- OpenAI describes long-horizon Codex work as a disciplined loop of plan, edit, run tools, observe, repair, update docs, and repeat: [Run long horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)
- Codex also exposes integrated git, terminal, worktree, and verification behavior in one task thread: [Codex app features](https://developers.openai.com/codex/app/features/)
- Cursor explicitly says long-running agents work better when they propose a plan first and use multiple agents to follow through on larger tasks: [Cursor long-running agents](https://www.cursor.com/blog/long-running-agents)
- METR's time-horizon work is a strong reminder that what matters now is how long an agent can stay coherent on real tasks, not just how good a single answer sounds: [METR time-horizon research](https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks)

Nala should align to that future directly.

## Target Loop

The canonical `/agent` execution path should become:

1. Scope the objective
2. Gather graph, git, and repo context
3. Draft a plan
4. Estimate blast radius and risks
5. Ask for approval
6. Execute edits in bounded batches
7. Run verification commands
8. Repair failures when appropriate
9. Present a review summary
10. Persist artifacts for later resume or handoff

## Implementation Steps

### Step 1: Planning phase

Use the new runtime from Mission 28 to generate a plan containing:

- objective
- scope
- candidate files
- graph-aware blast radius
- expected validations
- risks and assumptions

Leverage:

- `python-orchestrator/nala_orchestrator/startup.py`
- `python-orchestrator/nala_orchestrator/git_ops.py`
- `python-orchestrator/nala_orchestrator/graph/`
- `python-orchestrator/nala_orchestrator/tasks/ledger.py`

### Step 2: Approval phase

Before execution, the agent should show:

- files it intends to touch
- what kind of changes it will make
- what might break
- what verification it intends to run

The user can:

- approve
- ask for a narrower scope
- reject
- request a re-plan

### Step 3: Execution phase

Execution should use the existing action and multi-agent infrastructure where helpful, but route it through the `/agent` runtime:

- single-file safe edits may use the action executor
- larger structured work may use the multi-agent lead and worker flow

The user should not have to care which internal mechanism is used.

### Step 4: Verification phase

After execution, `/agent verify` should run or recommend repo-appropriate commands based on detected project type and local tooling.

Examples:

- Rust: `cargo test`, targeted crate tests, `cargo check`
- Python: `pytest`, `ruff`, `mypy`
- Node: `npm test`, `pnpm test`, `npm run lint`, `tsc`

Use repo detection and recipes, not hardcoded one-size-fits-all behavior.

### Step 5: Review phase

After verification, present:

- changed files
- diff summary
- commands run
- pass/fail results
- remaining concerns
- suggested next step

This should feed both the TUI workbench and session artifacts.

### Step 6: Failure-repair loop

If verification fails, the runtime should be able to:

- capture the failure
- decide whether an automatic repair attempt is safe
- retry within bounded limits
- escalate to the user when confidence is low

## Files To Change

- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/state.py`
- `python-orchestrator/nala_orchestrator/agents/orchestrator.py`
- `python-orchestrator/nala_orchestrator/agents/action_executor.py`
- `python-orchestrator/nala_orchestrator/git_ops.py`
- `python-orchestrator/nala_orchestrator/tasks/ledger.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/python_bridge.rs`
- `rust-core/nala-tui/src/ui/diff.rs`

## Acceptance Criteria

- [x] `/agent <objective>` creates a scoped plan before editing
- [x] The user must approve before execution begins
- [x] Execution happens in bounded batches with artifact tracking
- [x] Verification is a first-class phase, not an afterthought
- [x] Failures are summarized clearly and can trigger a bounded repair loop
- [x] The final summary explains what changed, what passed, what failed, and what remains risky

## Estimated Complexity

High. This is the core behavior mission for the optional autonomous agent workflow.
