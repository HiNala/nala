# HiNala Release Checklist

Use this checklist before tagging a release.

## Boot and install

- [ ] `scripts/setup.ps1` completes on Windows and installs `HiNala` launcher.
- [ ] `scripts/setup.sh` completes on Linux/macOS and installs `HiNala` launcher.
- [ ] New terminal can run `HiNala` from any project directory.
- [ ] `NALA_PYTHON` override works when default `python` is not suitable.

## Core quality gates

- [ ] `cargo fmt --manifest-path rust-core/Cargo.toml --all -- --check`
- [ ] `cargo clippy --manifest-path rust-core/Cargo.toml --workspace -- -D warnings`
- [ ] `cargo test --manifest-path rust-core/Cargo.toml --workspace`
- [ ] `ruff check python-orchestrator/nala_orchestrator/`
- [ ] `ruff format --check python-orchestrator/nala_orchestrator/`
- [ ] `pytest -q python-orchestrator/tests`

## Runtime smoke tests

- [ ] `HiNala --help` shows expected branding and commands.
- [ ] Start app in a medium-size repo and run `/scan`, `/index`, `/analyze quick`.
- [ ] `/doctor` reports bridge + LLM status correctly.
- [ ] `/lsp status` and one of `/def`, `/refs`, `/hover` works on a supported project.
- [ ] `nala dashboard --path <project>` starts and `/health` returns OK.

## Large codebase checks

- [ ] Run `scripts/benchmark.ps1` (Windows) or `scripts/benchmark.sh` (Unix).
- [ ] First index and warm index timings are captured in release notes.
- [ ] Memory usage and responsiveness are acceptable during `/analyze`.

## Mission-completeness check

- [ ] Mission docs reviewed for regressions against accepted criteria.
- [ ] Known gaps are listed in release notes with explicit follow-up milestones.
