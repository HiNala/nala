# HiNala Production Readiness + Competitive Review

Date: 2026-04-02  
Scope: `HiNala` launcher flow, scan/index/dashboard smoke, mission-aligned product quality review.

## Executive Result

HiNala is now in a much stronger "daily-drivable" state for terminal-first coding workflows:

- Global launch command works via `hinala` / `HiNala` / `nala` on Windows.
- Scan + index are now reliable after startup (including post-scan indexing).
- Dashboard launch works from non-repo working directories.
- Python bridge reliability and diagnostics visibility were improved.

The product is fundamentally strongest where local-first code intelligence + deep static analysis + terminal UX overlap. It is currently weaker than top competitors in mature editing ergonomics, LSP diagnostics UX depth, and multi-agent/session automation polish.

## What Was Verified Live

1. Windows setup and one-command install
   - `.\scripts\setup.ps1` completed successfully.
2. Command launcher and aliases
   - `hinala --help` and `HiNala --help` both worked.
3. File-system scan + index on real codebase
   - `hinala scan` and `hinala index` executed from a subdirectory.
4. Dashboard startup from outside repo root
   - `hinala dashboard --port 3011` from `C:\Users\NalaBook\Desktop` started Uvicorn successfully.

## Competitive Positioning

## Where HiNala Is Better

- Terminal-native architecture with no Electron/browser dependency for core coding flow.
- Integrated static analysis perspectives beyond basic chat/edit loops.
- Mission-driven architecture with explicit graph + sessions + context compression roadmap.
- Strong polyglot indexing direction (Rust/Python/JS/TS/Go grammar support in indexer path).
- Better "local code intelligence first" positioning than generic chat shells.

## Where HiNala Is Worse (Today)

- Editing loop maturity vs Cursor/Claude Code/Codex CLI is behind:
  - less refined inline edit flows,
  - weaker ergonomics for rapid diff/apply/revert cycles,
  - fewer hardened guardrails around bulk changes.
- LSP UX depth lags top tools:
  - diagnostics lifecycle/caching/surface still not as mature.
- Collaboration and agent orchestration polish is less battle-tested than enterprise-grade products.
- TUI module size/complexity still high in core app state code.
- Benchmark and quality gates are improving but not yet at parity with top production agents.

## Vs Specific Tools (Short Form)

- Cursor: stronger UI polish + edit ergonomics; HiNala stronger terminal purity and custom pipeline control.
- Claude Code / Codex CLI / Gemini CLI: stronger conversational agent polish and broad ecosystem integrations; HiNala stronger on integrated local indexing/analysis stack ownership.
- OpenCode-style minimal CLIs: HiNala has deeper architecture and analysis ambitions; simpler tools still win on immediate reliability/ergonomics.
- Neovim: unbeatable editing speed/extensibility for experts; HiNala offers integrated AI+analysis workflow without plugin glue burden.

## Fundamental Differentiator

HiNala's differentiator is not "chat in terminal."  
It is a full terminal-native engineering intelligence loop:

scan -> index -> graph/context -> perspectives -> sessions -> actionable coding loop

When this loop is fully polished, HiNala can be a category-defining "analysis-first coding agent shell."

## Weak Points (Current)

1. LSP diagnostics and UX parity are incomplete.
2. Some workflows still rely on internals that need modularization (notably large TUI app file).
3. Mission 20-24 acceptance tests (context/handoff/compression quality metrics) need deeper automated proof.
4. Bulk edit and mission execution confirmations/history need more robust UX.
5. Performance baselines exist but need stricter CI gating thresholds.

## What Is Working Well

1. Core Rust/Python hybrid stack builds and runs.
2. Launch/install flow is now materially more robust cross-session on Windows.
3. Indexing path now reliably produces symbols even after a preceding scan.
4. Dashboard can be launched from arbitrary working directories.
5. Setup scripts are more idempotent and version-safe than before.

## Todo List (This Pass)

All items below were executed in this pass:

- [x] Fix Windows launcher recursion caused by case-insensitive `.cmd` collision.
- [x] Ensure setup adds launcher path for current shell session usage.
- [x] Fix dashboard launch path resolution from any current directory.
- [x] Pass explicit dashboard project root into server default query params.
- [x] Serialize Python IPC request handling to prevent interleaved stream corruption.
- [x] Capture Python bridge stderr to `.nala/logs/python-bridge.stderr.log`.
- [x] Fix setup version checks and idempotent `.venv` handling in both scripts.
- [x] Fix index no-op after `scan` by indexing discovered files when changed set is empty.
- [x] Rebuild + run smoke checks (`scan`, `index`, `dashboard`) and test/lint gates.

## Next High-Value Todos (Not Executed In This Pass)

- [ ] Split `rust-core/nala-tui/src/app.rs` into focused modules (mission 15 maintainability target).
- [ ] Add full LSP diagnostics caching/surfacing path and integration tests.
- [ ] Finish mission-08 chunking strategy UX and cache behavior in user-facing flow.
- [ ] Expand mission 20-24 metric tests (token accuracy, fact preservation, compression stability).
- [ ] Add strict CI perf thresholds for index/scan latency on representative repos.

