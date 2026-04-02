# Mission 34: Git Integration, Worktrees, And Review Flow

## Objective

Implement the roadmap's high-priority git integration work in a way that directly supports the `/agent` orchestration model.

This mission should give Nala enough SCM intelligence to:

- understand current uncommitted work
- compare branches and revisions
- use worktrees for safe parallel agent runs
- review diffs inside the terminal workflow
- prepare the user for commit/PR workflows without leaving Nala

## Why This Matters

The roadmap already identifies deeper git integration as a near-term priority:

```14:22:ROADMAP.md
### 3. Git Integration
Deeper git integration beyond churn analysis: commit-level diffs, branch comparisons, `git blame` annotation, and queries like "What changed between v1.0 and v2.0 and what is the risk?" Surface this data in the graph and in perspectives.
```

For the `/agent` model, this is not optional polish. It is a core safety and usability requirement. If the orchestrator cannot reason about dirty worktrees, branch divergence, isolated execution, and diff review, it cannot become a trustworthy coding teammate.

## External Research Context

This is another area where the market is already giving strong signals:

- Codex's app includes built-in git diff review, staging/reverting chunks, worktrees, and thread-local terminals: [Codex app features](https://developers.openai.com/codex/app/features/)
- Codex worktrees are specifically designed to let multiple tasks proceed safely in parallel: [Codex worktrees](https://developers.openai.com/codex/app/worktrees/)
- Cursor's long-running agents are evaluated partly by whether they produce mergeable PR-sized outputs, not just code snippets: [Cursor long-running agents](https://www.cursor.com/blog/long-running-agents)
- Claude Code and other terminal agents increasingly win or lose on whether they handle git state safely and predictably during autonomous work: [Claude Code](https://www.anthropic.com/claude-code/)

## Scope

### Baseline git capabilities

Add or strengthen support for:

- repo status
- staged vs unstaged vs untracked counts
- branch tracking and ahead/behind
- recent commit summaries
- commit-level diff summaries
- branch comparison summaries
- `git blame` lookups for files/lines

### Review capabilities

Expose review-friendly flows for:

- current diff review
- branch comparison review
- changed-file summaries
- risk annotations based on graph or perspective data

### Worktree capabilities

Add optional worktree support for `/agent` runs so:

- the user's foreground work remains untouched
- risky or parallel runs can stay isolated
- workers can operate independently without stomping on each other

## Implementation Steps

### Step 1: Expand git operations module

Extend or create:

- `python-orchestrator/nala_orchestrator/git_ops.py`
- `python-orchestrator/nala_orchestrator/git_review.py`

Support functions such as:

- `branch_compare(base, head)`
- `commit_diff(rev_a, rev_b)`
- `blame_summary(file_path, line_range)`
- `create_worktree(label)`
- `list_worktrees()`
- `cleanup_worktree(label)`

### Step 2: Surface git state in the agent runtime

The orchestrator should understand:

- whether the main repo is dirty
- whether the user is ahead or behind remote
- whether a worker should be run in the main repo or a worktree

### Step 3: Add `/agent review` and `/agent scm`

Use `/agent review` for the current run's pending changes and `/agent scm` for richer branch/worktree status.

This keeps SCM within the unified `/agent` experience rather than reintroducing command sprawl.

### Step 4: Use worktrees for spawned workers

Worker runs that edit code should be able to opt into worktree isolation when:

- the main repo is already dirty
- multiple workers will edit in parallel
- the change is high-risk or exploratory

## Files To Change

- `python-orchestrator/nala_orchestrator/git_ops.py`
- `python-orchestrator/nala_orchestrator/git_review.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/workers.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/ui/diff.rs`
- `README.md`
- `ROADMAP.md`

## Acceptance Criteria

- [x] `/agent` can reason about current git status, branch divergence, and recent commits
- [x] The user can review the current run's diff from within Nala
- [x] Branch comparisons and commit-level summaries are available
- [x] Worktree-backed agent execution is supported for isolated runs
- [x] Parallel worker edits can be isolated safely
- [x] The roadmap's git integration priority is reflected in the implementation docs

## Estimated Complexity

High. Git and worktree support are essential to making autonomous workflows safe enough for daily use.
