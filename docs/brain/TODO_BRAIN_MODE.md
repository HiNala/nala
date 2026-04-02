# Brain Mode Detailed Todo

## Objective
Ship Brain Mode as an optional, explicit deep-reasoning workflow while preserving Nala's fast default terminal UX.

## Execution checklist

- [x] Add Brain command entrypoint (`/brain`).
- [x] Add first Brain workflow commands:
  - [x] `/brain investigate <objective>`
  - [x] `/brain hotspot`
  - [x] `/brain review-diff`
  - [x] `/brain verify`
  - [x] `/brain status`
- [x] Add Brain commands to slash completion.
- [x] Add Brain usage to `/help`.
- [x] Add persistent Brain scaffolding:
  - [x] `.nala/brain/project-brief.md`
  - [x] `.nala/brain/scopes/rust-core.md` (if directory exists)
  - [x] `.nala/brain/scopes/python-orchestrator.md` (if directory exists)
  - [x] `.nala/brain/scopes/dashboard.md` (if directory exists)

## Pending (high priority)

- [ ] Add Brain state machine (`idle`, `planning`, `awaiting_approval`, `executing`, `verifying`, `completed`, `blocked`).
- [ ] Add review checkpoint UI for planned actions.
- [ ] Add verification profile resolver from repo detection.
- [ ] Add blast-radius and risk report before apply.
- [ ] Add Brain inbox (`.nala/brain/inbox.json`) for pending items.
- [ ] Add autonomy levels (`analyze_only`, `plan_only`, `propose`, `apply_safe`, `run_until_blocked`).
- [ ] Add worktree-backed runs for risky scopes.
- [ ] Add metrics (`time_to_plan`, `validation_pass_rate`, `acceptance_rate`).

## Guardrails

- Keep normal chat flow lightweight and unaffected.
- Do not auto-apply edits without explicit user approval.
- Always run verification for applied changes.
- Keep Brain artifacts durable and human-readable.
