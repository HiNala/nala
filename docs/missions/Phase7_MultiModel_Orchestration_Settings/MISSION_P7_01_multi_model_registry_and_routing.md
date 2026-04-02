# Phase 7 Mission 01: Multi-Model Registry And Intelligent Routing

## Objective

Build a model registry that discovers every LLM available from the user's configured API keys, catalogs each model's strengths, cost, and context limits, and lets the `/agent` orchestrator route different task types to different models automatically.

The end result: when the user launches HiNala, the system knows exactly which providers are live, which models are accessible, and which model is best suited for planning, coding, research, design, and review tasks.

## Why This Matters

Today Nala uses one provider and one model for everything. That means a Haiku-class task burns Opus-class tokens, a coding task runs on a research model, and a design task uses a code model. Every serious agentic coding product is moving toward multi-model routing because different models genuinely excel at different things:

- OpenCode Zen curates and benchmarks models specifically for coding agents and lets users select per-agent: [OpenCode Zen](https://opencode.ai/zen)
- OpenCode allows per-agent model overrides so plan agents use cheaper/faster models while build agents use stronger ones: [OpenCode agents](https://opencode.ai/docs/agents)
- Claude Code routes exploration tasks to Haiku and complex tasks to Opus/Sonnet automatically via built-in subagents: [Claude Code subagents](https://docs.claude.com/en/docs/claude-code/subagents)
- Complexity-based routing is now considered best practice: 70-80% of agent requests are simple enough for small models, 15-20% need mid-tier, and only 5-10% require flagships: [Multi-model routing patterns](https://www.grizzlypeaksoftware.com/library/multi-model-architectures-router-patterns-lmlktp56)

## Current State In Nala

The existing code already supports multiple providers but only uses one at a time:

- `python-orchestrator/nala_orchestrator/config.py` — `Config` has `llm_provider` (one of `anthropic`, `openai`, `google`, `ollama`) and per-provider model strings
- `python-orchestrator/nala_orchestrator/llm/provider.py` — `create_provider(config)` returns one provider based on `config.llm_provider`
- `python-orchestrator/nala_orchestrator/llm/anthropic_provider.py`, `openai_provider.py`, `google_provider.py`, `ollama_provider.py` — each wraps one SDK
- `python-orchestrator/nala_orchestrator/context/counter.py` — `MODEL_LIMITS` has a static dict of context window sizes but is disconnected from actual provider configs
- Workers in `multi_agent/spawner.py` share the same `Config` as the lead, so every agent uses the same model

## Model Landscape (As Of April 2026)

### OpenAI

| Model | Best For | Context | Approx Cost (input/output per 1M tok) |
|-------|----------|---------|----------------------------------------|
| GPT-5.4 | Flagship reasoning, planning, research | 1M | $2.50 / $15.00 |
| GPT-5.4 mini | Coding, edits, subagent work, debugging | 400K | $0.75 / $4.50 |
| GPT-5.4 nano | High-volume simple tasks, classification | 400K | $0.20 / $1.25 |
| GPT-5.3-Codex | Long-horizon autonomous coding | 200K | Codex subscription |

### Anthropic

| Model | Best For | Context | Approx Cost (input/output per 1M tok) |
|-------|----------|---------|----------------------------------------|
| Claude Opus 4.6 | Deep research, PRDs, architecture docs, mission writing | 1M | $5.00 / $25.00 |
| Claude Sonnet 4.6 | Coding with guardrails, multi-file edits | 1M | $3.00 / $15.00 |
| Claude Haiku 4.5 | Fast exploration, triage, summaries | 200K | $1.00 / $5.00 |

### Google Gemini

| Model | Best For | Context | Approx Cost (input/output per 1M tok) |
|-------|----------|---------|----------------------------------------|
| Gemini 3.1 Pro | Complex reasoning, long-context analysis | 2M | $2.00 / $12.00 |
| Gemini 2.5 Flash | Balanced coding and conversation | 1M | $0.30 / $2.50 |
| Gemini 2.0 Flash Lite | Fast cheap tasks, design ideation | 1M | $0.075 / $0.30 |

## Architecture

### Model Registry

Create a `ModelRegistry` that:

1. On first `/models` run (or first agent launch), probes each provider's API to confirm which keys are valid
2. Loads a bundled catalog of known models per provider with metadata (strengths, context, cost tier, recommended roles)
3. Stores the resolved registry at `.nala/models/registry.json` so it only needs to be rebuilt on `/models refresh`
4. Exposes a query API: "give me the best model for task type X within provider Y"

### Task Type Taxonomy

Define a small fixed set of task types for routing:

| Task Type | Description | Recommended Tier |
|-----------|-------------|------------------|
| `plan` | High-level architecture, PRDs, mission writing | Flagship (Opus / GPT-5.4 / Gemini Pro) |
| `code` | Implementation, edits, refactors, bug fixes | Mid-tier coding specialist (Sonnet / GPT-5.4 mini) |
| `explore` | Codebase search, read-only analysis, triage | Fast cheap (Haiku / GPT-5.4 nano / Flash Lite) |
| `research` | Web research, documentation gathering | Flagship with web tools |
| `design` | UI/UX design reasoning, layout, styling | Gemini (strong multimodal) or flagship |
| `review` | Code review, safety audit, verification | Mid-tier or flagship |
| `summarize` | Compaction, handoffs, session summaries | Fast cheap |

### Model Router

Create a `ModelRouter` that:

1. Accepts a task type
2. Consults the registry and user preferences
3. Returns the best available `(provider, model)` pair
4. Falls back gracefully if the preferred provider is unavailable

## Implementation Steps

### Step 1: Create model catalog module

New files:

- `python-orchestrator/nala_orchestrator/models/__init__.py`
- `python-orchestrator/nala_orchestrator/models/catalog.py` — bundled model metadata
- `python-orchestrator/nala_orchestrator/models/registry.py` — `ModelRegistry` class
- `python-orchestrator/nala_orchestrator/models/router.py` — `ModelRouter` class
- `python-orchestrator/nala_orchestrator/models/types.py` — `TaskType` enum, `ModelInfo` dataclass

### Step 2: Build the bundled catalog

Ship a static catalog of known models per provider. This avoids needing to call the API just to know what models exist. The catalog should include:

- model ID
- display name
- provider
- context window
- max output
- cost tier (cheap / mid / expensive)
- strengths tags (coding, planning, research, design, fast, multimodal)
- recommended task types

### Step 3: Add key validation

On `/models` or first agent launch, validate which API keys are present and working by making a lightweight API call to each configured provider.

### Step 4: Persist registry

Write resolved registry to `.nala/models/registry.json` so subsequent runs skip validation unless the user runs `/models refresh`.

### Step 5: Build the router

The router should:

1. Accept a `TaskType`
2. Check user preferences (if they set explicit overrides)
3. Check available models from registry
4. Return the best match
5. Log which model was chosen and why

### Step 6: Integrate with providers

Refactor `create_provider` so it can create providers for any available key, not just the single `llm_provider` in config. The orchestrator and worker spawner should be able to request different providers for different task types.

### Step 7: Add `/models` command

Add a TUI command that shows:

- which providers have valid keys
- which models are available per provider
- current routing defaults
- suggestions for missing keys

### Step 8: Wire into agent runtime

Update `python-orchestrator/nala_orchestrator/agent_runtime/manager.py` and `multi_agent/spawner.py` so:

- the orchestrator uses the planning model for plans
- workers use the coding model for edits
- exploration uses the fast model
- research uses the research model

## Files To Change

- `python-orchestrator/nala_orchestrator/models/__init__.py`
- `python-orchestrator/nala_orchestrator/models/catalog.py`
- `python-orchestrator/nala_orchestrator/models/registry.py`
- `python-orchestrator/nala_orchestrator/models/router.py`
- `python-orchestrator/nala_orchestrator/models/types.py`
- `python-orchestrator/nala_orchestrator/llm/provider.py`
- `python-orchestrator/nala_orchestrator/config.py`
- `python-orchestrator/nala_orchestrator/agents/orchestrator.py`
- `python-orchestrator/nala_orchestrator/multi_agent/spawner.py`
- `python-orchestrator/nala_orchestrator/agent_runtime/manager.py`
- `python-orchestrator/nala_orchestrator/cli.py`
- `rust-core/nala-tui/src/commands.rs`
- `rust-core/nala-tui/src/app.rs`

## Acceptance Criteria

- [x] `/models` shows all available providers, valid keys, and accessible models
- [x] The registry is persisted and only rebuilt on explicit refresh
- [x] The router can select different models for planning, coding, exploring, research, design, and review tasks
- [x] Workers can use a different model than the orchestrator
- [x] Missing API keys produce helpful suggestions, not silent failures
- [x] The system works with only one provider configured (graceful single-provider fallback)

## Estimated Complexity

High. This is foundational infrastructure that every later orchestration feature depends on.
