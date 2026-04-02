"""Model router — selects the best model for a given task type."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .catalog import find_model
from .types import CostTier, ModelInfo, Provider, TaskType

if TYPE_CHECKING:
    from .registry import ModelRegistry

log = logging.getLogger(__name__)


class RouteResult:
    """The outcome of a routing decision."""

    __slots__ = ("provider", "model_id", "model_info", "reason")

    def __init__(
        self,
        provider: Provider,
        model_id: str,
        model_info: ModelInfo | None,
        reason: str,
    ) -> None:
        self.provider = provider
        self.model_id = model_id
        self.model_info = model_info
        self.reason = reason

    def __repr__(self) -> str:
        return f"RouteResult({self.provider.value}/{self.model_id} — {self.reason})"


class ModelRouter:
    """Selects the best available model for a given task type.

    Resolution order:
    1. User override for this task type (if configured)
    2. Best-scoring model from available models in the registry
    3. Fallback to the user's primary configured model
    """

    def __init__(
        self,
        registry: ModelRegistry,
        overrides: dict[TaskType, tuple[str, str]] | None = None,
        primary_provider: str = "",
        primary_model: str = "",
    ) -> None:
        self._registry = registry
        self._overrides = overrides or {}
        self._primary_provider = primary_provider
        self._primary_model = primary_model

    def route(self, task: TaskType) -> RouteResult:
        """Determine the best (provider, model) for a task."""
        if task in self._overrides:
            prov_str, model_id = self._overrides[task]
            try:
                provider = Provider(prov_str)
            except ValueError:
                provider = Provider(self._primary_provider) if self._primary_provider else Provider.ANTHROPIC
            if self._registry.is_provider_available(provider):
                info = find_model(model_id)
                log.info("Route %s → %s/%s (user override)", task.value, provider.value, model_id)
                return RouteResult(provider, model_id, info, "user override")

        candidates = self._registry.available_models()
        if not candidates:
            return self._fallback(task, "no models available")

        scored = [(m, m.strength_score(task)) for m in candidates]
        scored.sort(key=lambda x: (-x[1], x[0].input_cost_per_mtok))

        if scored and scored[0][1] > 0:
            best = scored[0][0]
            log.info(
                "Route %s → %s/%s (score=%d)",
                task.value, best.provider.value, best.id, scored[0][1],
            )
            return RouteResult(best.provider, best.id, best, f"best score ({scored[0][1]})")

        return self._fallback(task, "no model scored for task")

    def route_within_provider(self, task: TaskType, provider: Provider) -> RouteResult:
        """Route to the best model within a specific provider."""
        models = self._registry.available_models(provider)
        if not models:
            return self._fallback(task, f"no models for {provider.value}")

        scored = [(m, m.strength_score(task)) for m in models]
        scored.sort(key=lambda x: (-x[1], x[0].input_cost_per_mtok))
        best = scored[0][0]
        return RouteResult(best.provider, best.id, best, f"best in {provider.value} (score={scored[0][1]})")

    def format_routing_table(self) -> str:
        """Human-readable table showing current routing decisions."""
        lines = ["## Model Routing\n"]
        lines.append("| Task | Provider | Model | Reason |")
        lines.append("|------|----------|-------|--------|")
        for task in TaskType:
            result = self.route(task)
            lines.append(
                f"| {task.value} | {result.provider.value} | {result.model_id} | {result.reason} |"
            )
        lines.append("")
        if self._overrides:
            lines.append("_User overrides active for: "
                         + ", ".join(t.value for t in self._overrides) + "_")
        return "\n".join(lines)

    def _fallback(self, task: TaskType, reason: str) -> RouteResult:
        """Fall back to the primary configured model."""
        prov = self._primary_provider or "anthropic"
        model = self._primary_model or "claude-sonnet-4-6"
        try:
            provider = Provider(prov)
        except ValueError:
            provider = Provider.ANTHROPIC
        info = find_model(model)
        log.info("Route %s → %s/%s (fallback: %s)", task.value, prov, model, reason)
        return RouteResult(provider, model, info, f"fallback — {reason}")
