"""Core types for the multi-model registry and routing system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskType(str, Enum):
    """Fixed taxonomy of agent task types for model routing."""

    PLAN = "plan"
    CODE = "code"
    EXPLORE = "explore"
    RESEARCH = "research"
    DESIGN = "design"
    REVIEW = "review"
    SUMMARIZE = "summarize"


class CostTier(str, Enum):
    """Relative cost classification for model selection."""

    CHEAP = "cheap"
    MID = "mid"
    EXPENSIVE = "expensive"


class Provider(str, Enum):
    """Supported LLM provider identifiers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    OLLAMA = "ollama"


@dataclass(frozen=True)
class ModelInfo:
    """Metadata for a single LLM model."""

    id: str
    display_name: str
    provider: Provider
    context_window: int
    max_output: int
    cost_tier: CostTier
    strengths: frozenset[str] = field(default_factory=frozenset)
    recommended_tasks: frozenset[TaskType] = field(default_factory=frozenset)
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0

    def supports_task(self, task: TaskType) -> bool:
        return task in self.recommended_tasks

    def strength_score(self, task: TaskType) -> int:
        """Higher = better fit. Used by router for ranking."""
        score = 0
        if task in self.recommended_tasks:
            score += 10
        tag_map = {
            TaskType.PLAN: {"planning", "reasoning", "architecture"},
            TaskType.CODE: {"coding", "edits", "debugging"},
            TaskType.EXPLORE: {"fast", "triage", "exploration"},
            TaskType.RESEARCH: {"research", "web", "reasoning"},
            TaskType.DESIGN: {"multimodal", "design", "creative"},
            TaskType.REVIEW: {"review", "safety", "coding"},
            TaskType.SUMMARIZE: {"fast", "summarization", "cheap"},
        }
        relevant = tag_map.get(task, set())
        score += len(self.strengths & relevant) * 3
        if task in (TaskType.EXPLORE, TaskType.SUMMARIZE) and self.cost_tier == CostTier.CHEAP:
            score += 5
        if task == TaskType.PLAN and self.cost_tier == CostTier.EXPENSIVE:
            score += 3
        return score


@dataclass
class ProviderStatus:
    """Runtime status of a provider after key validation."""

    provider: Provider
    key_present: bool = False
    key_valid: bool = False
    available_models: list[str] = field(default_factory=list)
    error: str | None = None
