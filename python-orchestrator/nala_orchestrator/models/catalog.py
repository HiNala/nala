"""Bundled catalog of known models per provider.

This static catalog avoids needing API calls just to know what models exist.
Updated for the model landscape as of early 2026.
"""

from __future__ import annotations

from .types import CostTier, ModelInfo, Provider, TaskType

# ── Anthropic ───────────────────────────────────────────────────────────────

_ANTHROPIC_MODELS = [
    ModelInfo(
        id="claude-opus-4-6",
        display_name="Claude Opus 4.6",
        provider=Provider.ANTHROPIC,
        context_window=200_000,
        max_output=4_096,
        cost_tier=CostTier.EXPENSIVE,
        strengths=frozenset({"planning", "reasoning", "architecture", "research", "review"}),
        recommended_tasks=frozenset({TaskType.PLAN, TaskType.RESEARCH, TaskType.REVIEW}),
        input_cost_per_mtok=15.0,
        output_cost_per_mtok=75.0,
    ),
    ModelInfo(
        id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        provider=Provider.ANTHROPIC,
        context_window=200_000,
        max_output=8_192,
        cost_tier=CostTier.MID,
        strengths=frozenset({"coding", "edits", "debugging", "review", "reasoning"}),
        recommended_tasks=frozenset({TaskType.CODE, TaskType.REVIEW, TaskType.PLAN}),
        input_cost_per_mtok=3.0,
        output_cost_per_mtok=15.0,
    ),
    ModelInfo(
        id="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        provider=Provider.ANTHROPIC,
        context_window=200_000,
        max_output=4_096,
        cost_tier=CostTier.CHEAP,
        strengths=frozenset({"fast", "triage", "exploration", "summarization", "cheap"}),
        recommended_tasks=frozenset({TaskType.EXPLORE, TaskType.SUMMARIZE}),
        input_cost_per_mtok=1.0,
        output_cost_per_mtok=5.0,
    ),
]

# ── OpenAI ──────────────────────────────────────────────────────────────────

_OPENAI_MODELS = [
    ModelInfo(
        id="gpt-4o",
        display_name="GPT-4o",
        provider=Provider.OPENAI,
        context_window=128_000,
        max_output=16_384,
        cost_tier=CostTier.MID,
        strengths=frozenset({"coding", "reasoning", "planning", "review", "multimodal"}),
        recommended_tasks=frozenset({TaskType.CODE, TaskType.PLAN, TaskType.REVIEW}),
        input_cost_per_mtok=2.50,
        output_cost_per_mtok=10.0,
    ),
    ModelInfo(
        id="gpt-4o-mini",
        display_name="GPT-4o Mini",
        provider=Provider.OPENAI,
        context_window=128_000,
        max_output=16_384,
        cost_tier=CostTier.CHEAP,
        strengths=frozenset({"fast", "coding", "edits", "triage", "cheap"}),
        recommended_tasks=frozenset({TaskType.CODE, TaskType.EXPLORE, TaskType.SUMMARIZE}),
        input_cost_per_mtok=0.15,
        output_cost_per_mtok=0.60,
    ),
    ModelInfo(
        id="o3-mini",
        display_name="o3-mini",
        provider=Provider.OPENAI,
        context_window=200_000,
        max_output=100_000,
        cost_tier=CostTier.MID,
        strengths=frozenset({"reasoning", "planning", "coding", "architecture"}),
        recommended_tasks=frozenset({TaskType.PLAN, TaskType.CODE, TaskType.REVIEW}),
        input_cost_per_mtok=1.10,
        output_cost_per_mtok=4.40,
    ),
]

# ── Google Gemini ───────────────────────────────────────────────────────────

_GOOGLE_MODELS = [
    ModelInfo(
        id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        provider=Provider.GOOGLE,
        context_window=1_000_000,
        max_output=8_192,
        cost_tier=CostTier.CHEAP,
        strengths=frozenset({"fast", "multimodal", "coding", "design", "cheap"}),
        recommended_tasks=frozenset({TaskType.EXPLORE, TaskType.DESIGN, TaskType.SUMMARIZE}),
        input_cost_per_mtok=0.10,
        output_cost_per_mtok=0.40,
    ),
    ModelInfo(
        id="gemini-2.5-pro-preview-05-06",
        display_name="Gemini 2.5 Pro",
        provider=Provider.GOOGLE,
        context_window=1_000_000,
        max_output=65_536,
        cost_tier=CostTier.MID,
        strengths=frozenset({"reasoning", "coding", "planning", "multimodal", "research"}),
        recommended_tasks=frozenset({TaskType.PLAN, TaskType.CODE, TaskType.RESEARCH}),
        input_cost_per_mtok=1.25,
        output_cost_per_mtok=10.0,
    ),
    ModelInfo(
        id="gemini-2.0-flash-lite",
        display_name="Gemini 2.0 Flash Lite",
        provider=Provider.GOOGLE,
        context_window=1_000_000,
        max_output=8_192,
        cost_tier=CostTier.CHEAP,
        strengths=frozenset({"fast", "cheap", "summarization", "triage", "exploration"}),
        recommended_tasks=frozenset({TaskType.EXPLORE, TaskType.SUMMARIZE}),
        input_cost_per_mtok=0.075,
        output_cost_per_mtok=0.30,
    ),
]

# ── Ollama (local) ──────────────────────────────────────────────────────────

_OLLAMA_MODELS = [
    ModelInfo(
        id="codellama:13b",
        display_name="CodeLlama 13B",
        provider=Provider.OLLAMA,
        context_window=16_000,
        max_output=4_096,
        cost_tier=CostTier.CHEAP,
        strengths=frozenset({"coding", "fast", "local", "cheap"}),
        recommended_tasks=frozenset({TaskType.CODE, TaskType.EXPLORE}),
    ),
    ModelInfo(
        id="llama3:8b",
        display_name="Llama 3 8B",
        provider=Provider.OLLAMA,
        context_window=8_000,
        max_output=4_096,
        cost_tier=CostTier.CHEAP,
        strengths=frozenset({"fast", "local", "cheap", "triage"}),
        recommended_tasks=frozenset({TaskType.EXPLORE, TaskType.SUMMARIZE}),
    ),
    ModelInfo(
        id="deepseek-coder-v2:16b",
        display_name="DeepSeek Coder V2 16B",
        provider=Provider.OLLAMA,
        context_window=32_000,
        max_output=4_096,
        cost_tier=CostTier.CHEAP,
        strengths=frozenset({"coding", "edits", "debugging", "local"}),
        recommended_tasks=frozenset({TaskType.CODE, TaskType.REVIEW}),
    ),
]

# ── Combined catalog ────────────────────────────────────────────────────────

BUNDLED_CATALOG: dict[Provider, list[ModelInfo]] = {
    Provider.ANTHROPIC: _ANTHROPIC_MODELS,
    Provider.OPENAI: _OPENAI_MODELS,
    Provider.GOOGLE: _GOOGLE_MODELS,
    Provider.OLLAMA: _OLLAMA_MODELS,
}

ALL_MODELS: list[ModelInfo] = [
    m for models in BUNDLED_CATALOG.values() for m in models
]


def find_model(model_id: str) -> ModelInfo | None:
    """Look up a model by its ID across all providers."""
    for m in ALL_MODELS:
        if m.id == model_id:
            return m
    return None


def models_for_provider(provider: Provider) -> list[ModelInfo]:
    """Return all known models for a provider."""
    return list(BUNDLED_CATALOG.get(provider, []))
