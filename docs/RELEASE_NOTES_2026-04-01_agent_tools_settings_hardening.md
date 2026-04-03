# Release Notes — 2026-04-01

This update hardens agent tooling, settings wiring, and command UX so HiNala works more reliably out of the box.

## Highlights

- Fixed task ledger integration bug in `Toolbox` (`task.id` -> `task.task_id`).
- Fixed `Toolbox.run_analysis()` to use the actual `PerspectivesEngine` API (`run_quick`, `run_all`, `run_one`).
- Added practical toolbox file utilities:
  - `read_file(path)`
  - `search_code(query)`
  - `list_files(directory)`
- Expanded agent system prompt with explicit tool awareness so `/agent` runs can use the right capabilities.
- Wired settings into runtime behavior:
  - `agent.autonomy` default now respected for `/agent objective` (with legacy `guided` normalized to `plan`)
  - `agent.max_workers` now drives `WorkerRegistry` limits
  - `agent.git.auto_branch`, `agent.git.branch_prefix`, `agent.git.auto_commit` now influence mission runs
  - `agent.verification.verify_timeout` now controls verification shell command timeouts
  - `display.show_startup_hints` now controls startup suggestions
- Improved startup intelligence:
  - Key detection now checks both `.env` and `.nala/settings.toml`.
- Improved `/settings` UX:
  - `/settings setup` now provides clear, step-by-step onboarding instructions.
  - Validation added for `models.default_provider`.
  - Validation added for `models.routing.*` format (`provider/model` or `provider:model`).
- Improved defaults / first-run behavior:
  - Auto-detect provider from available keys if no explicit provider is set.
  - Auto-create default `.nala/settings.toml` during scaffold setup when missing.
- Improved command surface:
  - `/act` now uses action-mode query path (`query_with_actions`) as intended.
  - Restored practical aliases:
    - `/diff` -> `/agent review`
    - `/status` -> `/agent status`
    - `/branch` -> `/agent scm`
    - `/task` -> `/agent status`
    - `/team` -> worker-focused `/agent` mapping
- Added clearer guardrails when no LLM is configured for `/agent start` and `/agent objective`.

## Verification

- Rust: `cargo check` passes.
- Python: `pytest` passes (`32 passed`).
- Python syntax checks (`py_compile`) pass on all modified orchestrator files.

