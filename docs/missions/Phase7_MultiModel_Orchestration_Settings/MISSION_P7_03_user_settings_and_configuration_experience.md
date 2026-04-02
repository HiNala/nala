# Phase 7 Mission 03: User Settings And Configuration Experience

## Objective

Create a complete settings system so the user can configure their API keys, model preferences, task-type routing, autonomy levels, git behavior, and agent defaults from inside Nala, without manually editing `.env` files or JSON.

The settings should persist across sessions, support project-level overrides, and integrate with the model registry and orchestration layer built in the previous two missions.

## Why This Matters

Right now all configuration lives in `.env` files and hardcoded defaults inside `config.py`. That works for developers building Nala itself, but not for users who want to:

- add API keys without opening a text editor
- pick which model handles coding vs. planning vs. design
- set autonomy preferences (how much to approve vs. auto-run)
- configure git behavior for agent runs
- see what is configured and what is missing

Every serious coding tool now has a configuration surface:

- Windsurf uses `AGENTS.md` and `.windsurf/rules/` for scoped instructions: [Windsurf AGENTS.md](https://docs.windsurf.com/windsurf/cascade/agents-md)
- OpenCode uses `opencode.json` with per-agent model overrides, permissions, temperature, and tool access: [OpenCode agents](https://opencode.ai/docs/agents)
- Codex uses local environment configs, sandbox settings, and skill definitions: [Codex app features](https://developers.openai.com/codex/app/features/)

Nala needs its own version that fits the terminal-first philosophy.

## Current State In Nala

- `python-orchestrator/nala_orchestrator/config.py` — `Config` loads from `.env` with `dotenv`, supports per-provider model strings, Neo4j, dashboard settings
- `.env.example` — documents available keys but is incomplete
- No `/config` or `/settings` command exists yet
- The roadmap already identifies a "Configuration UI" as a near-term item
- No way to set model routing preferences, autonomy levels, or per-task-type model assignments

## Settings File Format

Introduce `.nala/settings.toml` as the canonical user-facing configuration file.

```toml
[keys]
# API keys (can also be set via env vars — env vars take precedence)
anthropic_api_key = "sk-ant-..."
openai_api_key = "sk-..."
google_api_key = "AI..."

[models]
# Default provider when no task-specific routing applies
default_provider = "anthropic"
default_model = "claude-sonnet-4-6"

[models.routing]
# Task-type → provider/model overrides
plan = "anthropic/claude-opus-4-6"
code = "anthropic/claude-sonnet-4-6"
explore = "anthropic/claude-haiku-4-5"
research = "openai/gpt-5.4"
design = "google/gemini-2.5-flash"
review = "anthropic/claude-sonnet-4-6"
summarize = "anthropic/claude-haiku-4-5"

[agent]
# Default autonomy level: "manual" | "guided" | "autonomous"
autonomy = "guided"
# Max workers the orchestrator can spawn
max_workers = 3

[agent.git]
# Auto-create branches for agent runs
auto_branch = true
# Auto-commit verified milestones
auto_commit = true
# Branch prefix
branch_prefix = "nala/agent-"

[agent.verification]
# Auto-run verification after edits
auto_verify = true
# Timeout for verification commands (seconds)
verify_timeout = 120

[display]
# Theme preference
theme = "dark"
# Show startup intelligence on boot
show_startup_hints = true
```

## Implementation Steps

### Step 1: Create settings loader

New files:

- `python-orchestrator/nala_orchestrator/settings/__init__.py`
- `python-orchestrator/nala_orchestrator/settings/loader.py`
- `python-orchestrator/nala_orchestrator/settings/schema.py`
- `python-orchestrator/nala_orchestrator/settings/writer.py`

The loader should:

1. Read `.nala/settings.toml` if it exists
2. Fall back to `.env` values for API keys
3. Fall back to hardcoded defaults for everything else
4. Merge project-level settings with global `~/.nala/settings.toml`

### Step 2: Add `/settings` command in the TUI

Add a `/settings` command that shows a readable summary of current configuration:

```
Provider keys:
  ✓ Anthropic (claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5)
  ✓ OpenAI (gpt-5.4, gpt-5.4-mini, gpt-5.4-nano)
  ✗ Google (no key configured)
  ✗ Ollama (not running)

Model routing:
  plan     → claude-opus-4-6
  code     → claude-sonnet-4-6
  explore  → claude-haiku-4-5
  research → gpt-5.4
  design   → (no Google key — fallback: claude-sonnet-4-6)

Agent defaults:
  autonomy   → guided
  max workers → 3
  git: auto-branch ✓  auto-commit ✓
```

### Step 3: Add `/settings set <key> <value>`

Support inline configuration changes:

- `/settings set keys.openai_api_key sk-...`
- `/settings set models.routing.plan openai/gpt-5.4`
- `/settings set agent.autonomy autonomous`

Changes should be written to `.nala/settings.toml` immediately.

### Step 4: Add `/settings setup` wizard

A guided first-run setup that walks the user through:

1. Paste your API keys (Anthropic, OpenAI, Google)
2. Choose a default provider
3. Accept recommended routing or customize
4. Choose autonomy level
5. Configure git preferences

This should run automatically on first `/agent` invocation if no settings exist.

### Step 5: Integrate with Config and ModelRouter

Refactor `Config.load()` to read from `.nala/settings.toml` in addition to `.env`:

- `.env` keys take precedence over settings.toml keys (so env vars always win)
- settings.toml provides the richer structured configuration that `.env` cannot express

The `ModelRouter` from Mission P7-01 should read routing preferences from settings.

### Step 6: Add scoped settings

Support project-level overrides in `.nala/settings.toml` that take precedence over the global `~/.nala/settings.toml`.

### Step 7: Integrate with interpreter suggestions

Update `python-orchestrator/nala_orchestrator/startup.py` so startup intelligence uses settings:

- if keys are missing, suggest `/settings setup`
- if routing has fallbacks, mention them
- if the user has never configured settings, prompt once

## Files To Change

- `python-orchestrator/nala_orchestrator/settings/__init__.py`
- `python-orchestrator/nala_orchestrator/settings/loader.py`
- `python-orchestrator/nala_orchestrator/settings/schema.py`
- `python-orchestrator/nala_orchestrator/settings/writer.py`
- `python-orchestrator/nala_orchestrator/config.py`
- `python-orchestrator/nala_orchestrator/models/router.py`
- `python-orchestrator/nala_orchestrator/startup.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`
- `rust-core/nala-tui/src/python_bridge.rs`
- `.env.example`
- `README.md`

## Acceptance Criteria

- [ ] `.nala/settings.toml` is the canonical configuration file
- [ ] `/settings` shows a complete, readable summary of current configuration
- [ ] `/settings set` allows inline changes that persist
- [ ] `/settings setup` provides a guided first-run wizard
- [ ] Model routing preferences are respected by the orchestrator and workers
- [ ] Missing keys produce helpful suggestions, not crashes
- [ ] Project-level settings override global settings
- [ ] API keys from `.env` still work and take precedence

## Estimated Complexity

Medium. The settings infrastructure is well-understood engineering, but the integration with the model registry and orchestrator requires careful layering.
