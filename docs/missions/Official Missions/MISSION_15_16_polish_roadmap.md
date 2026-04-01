# Mission 15: Review, Polish, and Harden

## Objective

Conduct a comprehensive review of the entire Nala codebase and product, fix all rough edges, improve error handling, add missing tests, optimize performance, clean up documentation, and ensure every component works cohesively. This is the "make it actually good" mission.

## Why This Matters

The difference between a project that impresses and one that embarrasses is in the details. Missing error messages, unhandled edge cases, inconsistent formatting, slow startup on certain platforms, confusing command output -- these small things compound into the feeling of "this was rushed." This mission ensures that Nala feels like it was built by someone who cared about every detail.

## Implementation Steps

### Step 1: Code quality sweep

Run through every source file in both Rust and Python and verify:
- No file exceeds 400-600 lines. Split any that do.
- All public functions have doc comments (Rust) or docstrings (Python)
- No TODO/FIXME/HACK comments remain without a linked issue
- All error types have human-readable messages
- No unwrap() calls in Rust production code (use proper error handling with ? and anyhow/thiserror)
- No bare except or except Exception in Python (catch specific exceptions)
- Consistent naming conventions throughout (snake_case in Rust and Python, no mixed styles)

### Step 2: Error handling hardening

Review every error path and ensure:
- File not found errors show the path that was not found
- Permission errors suggest running with appropriate permissions
- Network errors (Neo4j, LLM APIs) show connection details and suggest fixes
- Configuration errors show which config value is wrong and what it should be
- Parse errors show the file path, line number, and a snippet of the problematic code
- Every error message is actionable (tells the user what to do, not just what went wrong)

### Step 3: Performance optimization

Profile and optimize:
- Startup time: Target under 2 seconds to first usable frame
- Indexing: Verify 100k-line codebase indexes in under 30 seconds (first run) and under 2 seconds (incremental)
- TUI rendering: Verify no frame drops during normal operation using Ratatui's benchmark tools
- Memory usage: Profile with large codebases. Ensure no memory leaks in long-running sessions.
- Graph queries: Verify Neo4j queries on a 10,000-node graph return in under 500ms

### Step 4: Test coverage

Add or improve tests for:
- Rust unit tests for scanner, hasher, parser, metrics, cache, LSP client
- Rust integration tests for the full scan-parse-index pipeline
- Python unit tests for each perspective
- Python integration tests for session management and report generation
- End-to-end test: boot Nala on a sample project, run an analysis, verify a report is generated
- Edge cases: empty projects, projects with no supported language files, binary files, symlinks, very large files

### Step 5: Documentation

- README.md: Installation instructions, quick start guide, feature overview, screenshots/GIFs
- CONTRIBUTING.md: How to set up the dev environment, coding standards, PR process
- Each crate's lib.rs should have a module-level doc comment explaining its purpose
- The Python package should have a top-level docstring explaining the orchestration layer
- CLI help text should be clear and complete for every subcommand and flag

### Step 6: Polish the TUI

- Consistent color scheme across all panels and modes
- Smooth transitions between modes (no flickering or partial renders)
- Helpful empty states (when no sessions exist, when Neo4j is not connected, when no LLM is configured)
- Keyboard shortcut help overlay (show on `?` key)
- Loading indicators for all async operations (indexing, analysis, LLM calls)
- Graceful terminal restoration on crash (install panic hook that restores terminal mode)

### Step 7: Cross-platform testing

Test on:
- macOS (ARM and Intel)
- Ubuntu 22.04+ (x86_64)
- Windows 11 with WSL2
- Various terminal emulators: iTerm2, Alacritty, Kitty, Windows Terminal, default macOS Terminal

### Step 8: Security review

- API keys are never logged or displayed in the TUI
- The `.nala/` directory has appropriate permissions (0700)
- No code is sent to external APIs unless the user has explicitly configured an LLM provider
- SQLite database is not world-readable

## Acceptance Criteria

- All tests pass on all supported platforms
- No unwrap() calls in Rust production code
- Every error message is actionable
- README covers installation and quick start
- Startup time is under 2 seconds
- No file exceeds 400-600 lines
- A developer unfamiliar with the project can clone, build, and use Nala by following the README

---

# Mission 16: What's Next (Future Vision and Roadmap)

## Objective

Document the future roadmap for Nala, including features that are planned but not yet built, research areas, and long-term vision. This document lives in the repo as ROADMAP.md and serves as both a guide for future development and a communication tool for potential contributors and users.

## Roadmap Items

### Near-Term (Next 3 Months)

1. **Additional Language Support**: Add Tree-sitter grammars and symbol extractors for Java, C/C++, Ruby, PHP, Kotlin, Swift, C#. Each language is a small, scoped mission.

2. **MCP Server Mode**: Expose Nala's indexing, analysis, and graph features as an MCP (Model Context Protocol) server. This lets other AI tools (Claude Code, Cursor, OpenCode) use Nala as a backend for codebase understanding.

3. **Git Integration**: Deeper git integration beyond churn analysis. Show blame information, branch comparisons, and commit-level analysis. "What changed between v1.0 and v2.0 and what is the risk?"

4. **Configuration UI**: A `/config` command in the TUI that lets users configure perspectives, thresholds, LLM provider, and other settings interactively without editing TOML files.

5. **Plugin System**: Allow users to write custom perspectives as Python scripts that Nala discovers and runs alongside built-in perspectives.

### Medium-Term (3-6 Months)

6. **Custom Model Training**: Build a pipeline for fine-tuning smaller models (7B-13B parameter) on code analysis tasks. Train models that excel at specific perspectives (complexity explanation, refactoring suggestions, security analysis). Run them locally via Ollama.

7. **Multi-Model Chains**: Chain multiple models together for higher-quality analysis. A fast model does initial triage, a specialized model does deep analysis on flagged areas, and a general model writes the human-readable report.

8. **Collaborative Sessions**: Share sessions with teammates. Upload session reports to a shared location. Compare sessions across team members.

9. **CI/CD Integration**: Run Nala as part of a CI pipeline. Fail the build if new code introduces findings above a configured severity threshold. Generate PR comments with analysis summaries.

10. **IDE Extensions**: Create lightweight extensions for VS Code, NeoVim, and JetBrains IDEs that connect to a running Nala instance for inline analysis results.

### Long-Term (6-12 Months)

11. **Self-Healing Codebase**: The ultimate vision. Nala continuously monitors the codebase, generates missions when problems are detected, and (with user permission) automatically applies fixes via agent actions. The developer reviews and approves changes rather than writing them.

12. **Cross-Repository Analysis**: Analyze multiple repositories as a unified system. Understand how microservices depend on each other, where API contracts might break, and which services are the most fragile.

13. **Architectural Pattern Recognition**: Teach Nala to recognize common architectural patterns (MVC, hexagonal, event-driven) and evaluate whether the codebase follows its own patterns consistently.

14. **Natural Language Codebase Documentation**: Generate and maintain documentation from the code graph. As the code changes, the documentation updates automatically.

## Document Deliverable

Create ROADMAP.md in the project root with all of the above, organized by timeline and priority. Each item includes a brief description, estimated effort, and dependencies on other items.
