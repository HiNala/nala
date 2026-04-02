# Mission 26: Brain Mode (Optional Secondary Workflow)

## Direction

Brain Mode is not an always-on daemon. It is an explicit, user-invoked workflow for deeper repo reasoning and guided execution, while the normal Nala loop remains fast and lightweight.

## Why this mission exists

Nala already has strong primitives (index, graph, perspectives, sessions, action mode, task ledger), but they are exposed as separate commands. This mission unifies those capabilities into one coherent objective-first workflow.

## Naming note

`/brain` is the baseline entrypoint introduced in this mission batch, but it is not intended to remain the long-term public command.

The next mission set consolidates the user-facing workflow under `/agent` so the product has one clear autonomous-workflow entrypoint instead of a growing set of overlapping slash commands.

## North Star

When a user invokes Brain Mode, Nala should behave like a careful senior engineer:
- scopes work clearly,
- proposes a plan before execution,
- executes with explicit boundaries,
- verifies outcomes,
- and leaves an auditable artifact trail.

## Initial implementation slice (completed in this batch)

### 1) Brain command surface in TUI
- Added `/brain` workflow entrypoint.
- Added `/brain investigate <objective>` to create a tracked task and start deep run.
- Added `/brain hotspot`, `/brain review-diff`, `/brain verify`, `/brain status`.
- Added Brain commands to slash completion.

### 2) Durable Brain artifacts
- Added startup scaffold generation in Python IPC startup:
  - `.nala/brain/project-brief.md`
  - `.nala/brain/scopes/rust-core.md` (if present)
  - `.nala/brain/scopes/python-orchestrator.md` (if present)
  - `.nala/brain/scopes/dashboard.md` (if present)

This establishes persistent memory/rules placeholders for Brain runs.

## 25-item implementation backlog (detailed)

1. Define Brain Mode as optional, user-invoked workflow.
2. Add explicit activation (`/brain`, keybind, or toggle).
3. Add dedicated Brain surface separate from regular chat.
4. Formalize brain runtime above index/graph/LSP/sessions/actions.
5. Separate tools, skills, plugins in orchestration model.
6. Create project brain state object.
7. Expand task ledger for objective lifecycle.
8. Add internal role model (Scout/Planner/Implementer/Verifier/Reviewer).
9. Enforce plan -> approve -> execute -> verify -> summarize.
10. Add graph-aware blast-radius queries to planning.
11. Build risk scorer (churn/complexity/diagnostics/centrality).
12. Add proactive-but-opt-in Brain suggestions.
13. Maintain `.nala/brain/project-brief.md`.
14. Add directory-scoped guidance files.
15. Build reusable Brain skills (triage/fix/refactor/review).
16. Add explicit autonomy levels.
17. Enrich action proposals with confidence, rollback, validation.
18. Make verification mandatory phase.
19. Build dedicated diff/review apply-revise flow.
20. Support worktree-backed Brain runs.
21. Improve persistence for pause/resume/fork/compare/handoff.
22. Create Brain inbox for pending/blocked/recommended work.
23. Add user-friendly Brain commands for core workflows.
24. Instrument metrics for UX and reliability.
25. Bake trust model into product behavior.

## Acceptance criteria for Mission 26 baseline

- [x] Brain entrypoint available in TUI command surface.
- [x] Brain command hints available in `/help`.
- [x] Brain command completion entries present.
- [x] Persistent Brain scaffolding artifacts created automatically on startup.
- [x] Core app remains functional after integration.

## Next milestones

1. Rename the public command surface from `/brain` to `/agent` and consolidate overlapping slash commands.
2. Promote Brain lifecycle into structured statuses (`planned`, `approved`, `executing`, `verifying`, `done`).
3. Add review checkpoint UI before apply.
4. Add command recipes for verify phase per detected repo type.
5. Add blast-radius report from graph before change execution.
