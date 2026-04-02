# Mission 29: Agent Workbench In The TUI

## Objective

Give `/agent` a dedicated, optional interface inside the terminal UI so autonomous work feels clear, inspectable, and controllable.

The user should not need to reconstruct agent state from a stream of generic chat messages. When `/agent` is active, Nala should show a focused workbench for plan review, task progress, approvals, verification, and summary artifacts.

## Why This Matters

Your own product direction is terminal-first, not terminal-only. That means the UX challenge is not "how do we add a second app," but "how do we expose a deeper workflow without making the main interface noisy?"

The current app already has the right building blocks:

- a panel-based layout in `rust-core/nala-tui/src/ui/layout.rs`
- stateful app mode and background events in `rust-core/nala-tui/src/app.rs`
- diff rendering in `rust-core/nala-tui/src/ui/diff.rs`
- command/help/status infrastructure in `rust-core/nala-tui/src/commands.rs`

What is missing is a coherent surface for the optional agent workflow.

## External Research Context

The best agentic products increasingly give long-running work its own inspectable surface:

- Codex's app highlights parallel task threads, diff review, integrated terminal output, git actions, and a floating window for focused work: [Codex app features](https://developers.openai.com/codex/app/features/)
- Claude Code's desktop experience emphasizes parallel tasks, visual diffs, preview servers, and PR monitoring in one place: [Claude Code](https://www.anthropic.com/claude-code/)
- Windsurf's Cascade keeps planning, queued messages, checkpoints, and error handling in one distinct assistant panel instead of scattering them across unrelated commands: [Cascade overview](https://docs.windsurf.com/windsurf/cascade/cascade)
- Sublime Text remains a useful UX reminder that responsiveness, split views, and fast navigation matter as much as intelligence: [Sublime Text features](https://www.sublimetext.com/features)

Nala should apply those lessons in a terminal-native form.

## UX Goal

When `/agent` is active, the user should be able to open a dedicated workbench that shows:

- current objective
- current phase (`planning`, `awaiting approval`, `executing`, `verifying`, etc.)
- scoped files and inferred blast radius
- active task list
- pending approvals
- latest verification command/output summary
- current diff review status

This workbench must remain optional. If the user never touches `/agent`, the normal Nala experience should stay lean.

## Recommended Interaction Model

Add a new optional panel or mode that can be toggled with a dedicated keybinding such as `Ctrl+G`.

Possible layout:

- left panel: file tree
- center: regular conversation or diff review
- right panel: agent workbench

Or, if the terminal width is too narrow:

- keep the current layout
- allow `/agent` to switch the main body into a workbench view until the user exits it

## Implementation Steps

### Step 1: Add agent UI state

Extend `rust-core/nala-tui/src/app.rs` with state for:

- `agent_panel_open`
- `agent_phase`
- `agent_objective`
- `agent_summary_lines`
- `agent_pending_approvals`
- `agent_scope_files`
- `agent_verification_summary`

### Step 2: Create a dedicated agent panel renderer

Add a new UI module such as:

- `rust-core/nala-tui/src/ui/agent_panel.rs`

It should render a compact, readable summary of the current `/agent` run rather than raw chat output.

### Step 3: Update the main layout

Refactor:

- `rust-core/nala-tui/src/ui/layout.rs`
- `rust-core/nala-tui/src/ui/status_bar.rs`

to support showing an agent workbench when relevant.

The status bar should indicate whether an agent run is idle, planning, waiting for approval, running, verifying, blocked, or done.

### Step 4: Add background events for agent updates

Extend the Rust app event model so the Python runtime can stream structured updates like:

- `AgentStatusUpdated`
- `AgentPlanReady`
- `AgentApprovalRequested`
- `AgentVerificationUpdated`
- `AgentRunCompleted`

Do not rely only on free-form assistant text for workbench rendering.

### Step 5: Reuse the diff UI for review checkpoints

When the agent reaches a review gate, the workbench should integrate with:

- `rust-core/nala-tui/src/ui/diff.rs`

so the user can inspect changes before continuing execution.

## Files To Change

- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/ui/layout.rs`
- `rust-core/nala-tui/src/ui/status_bar.rs`
- `rust-core/nala-tui/src/ui/diff.rs`
- `rust-core/nala-tui/src/ui/agent_panel.rs`
- `rust-core/nala-tui/src/python_bridge.rs`
- `python-orchestrator/nala_orchestrator/cli.py`
- `README.md`

## Acceptance Criteria

- [ ] `/agent` has a dedicated inspectable UI surface in the TUI
- [ ] The workbench shows objective, phase, tasks, and verification state
- [ ] The user can toggle the workbench on and off without breaking normal chat flow
- [ ] Diff review and approval can happen inside the same workflow
- [ ] The status bar clearly reflects active agent state
- [ ] Narrow terminals degrade gracefully

## Estimated Complexity

Medium to High. The widgets are manageable, but the interaction design has to stay simple and fast.
