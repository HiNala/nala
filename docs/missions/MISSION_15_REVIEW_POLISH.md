# Mission 15: Review, Polish, and Harden

## Objective

A thorough review pass: fix bugs, harden error paths, add missing tests, improve performance, and make Nala feel like a tool built by someone who genuinely cares about developer experience.

## Why This Mission Exists

Feature completeness is not the same as quality. A tool can have all the right capabilities and still feel rough around the edges. This mission is where Nala goes from "it works" to "it feels great." Inspired by Steve Jobs's obsession with the last 5% and Dieter Rams's principle that good design is long-lasting.

## Review Checklist

### Rust Core

- [ ] Run `cargo clippy --workspace -- -D warnings` with zero warnings
- [ ] Run `cargo test --workspace` with zero failures
- [ ] Check every `unwrap()` and `expect()` — replace with proper error handling
- [ ] Review all file size limits — no source file should exceed 400 lines
- [ ] Test TUI at 80-column width, 40-column width, and 300-column width
- [ ] Verify boot time < 500ms on a cold start
- [ ] Verify incremental scan < 2 seconds on a 50k-file project with no changes
- [ ] Review all `TODO (Mission N)` comments — are they still accurate?

### Python Orchestrator

- [ ] Run `ruff check python-orchestrator/` with zero errors
- [ ] Add type annotations to all public functions
- [ ] Add docstrings to all public classes and methods
- [ ] Test all four LLM providers with a real API key
- [ ] Test graceful degradation when Neo4j is not running
- [ ] Test graceful degradation when no API key is set
- [ ] Review session directory structure — is it clean and human-readable?

### User Experience

- [ ] First-run experience: is the message helpful when no .env exists?
- [ ] Error messages are actionable (tell the user what to do, not just what failed)
- [ ] Keyboard shortcuts are discoverable (status bar shows them correctly)
- [ ] Splash screen: does it feel professional?
- [ ] Help output `/help`: is it complete and accurate?
- [ ] Try Nala on a real large project (50k+ lines) — does it feel fast?

### Security

- [ ] API keys are never logged
- [ ] `.env` is in `.gitignore` (already done — verify)
- [ ] No shell injection in file path handling
- [ ] SQLite operations use parameterised queries (already done — verify)
- [ ] Session files do not contain secrets

### Documentation

- [ ] README.md is accurate and complete
- [ ] All mission files have correct acceptance criteria
- [ ] ARCHITECTURE.md is written (Mission 17)
- [ ] DATA_FLOW.md is written (Mission 18)
- [ ] EXTENSION_GUIDE.md is written (Mission 19)

## Performance Targets

| Operation | Target |
|-----------|--------|
| Cold boot to TUI | < 500ms |
| Incremental scan (no changes) | < 2s |
| First full index (100k lines) | < 30s |
| Symbol lookup by name | < 100ms |
| LLM first token (Anthropic) | < 3s |

## Common Issues to Check

1. **TUI flicker** — Ratatui should only redraw changed regions. Verify `DefaultTerminal` is using double-buffered rendering.
2. **Memory growth** — Message log in `app.rs` grows unbounded. Add a `MAX_MESSAGES` limit (e.g. 1000).
3. **Panic on resize** — Test terminal resize during active TUI. Should not panic.
4. **Large file handling** — Files > 1MB are filtered in `scanner.rs`. Verify this limit works.
5. **Unicode in paths** — Test with project paths containing Unicode characters.
6. **Windows line endings** — Tree-sitter handles CRLF correctly. Verify hashes are consistent.
