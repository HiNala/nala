"""Short-term memory manager (Layer 1).

Wraps the context window machinery and provides a clean API for the agent
to query what it currently knows in its working context.
"""

from __future__ import annotations

from ..context.background_summary import BackgroundSummary
from ..context.counter import TokenCounter


class ShortTermMemory:
    """Manages what the agent currently knows (context window layer)."""

    def __init__(self) -> None:
        self._counter = TokenCounter()
        self._background = BackgroundSummary()
        self._injected: list[dict] = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_turn(self, history: list[dict]) -> None:
        """Call after every conversation turn to keep the background summary fresh."""
        self._background.on_turn(history)

    # ── Context injection ─────────────────────────────────────────────────────

    def inject_context(self, content: str, category: str = "general") -> None:
        """Add a piece of context to working memory."""
        self._injected.append({"category": category, "content": content})

    def clear_injected(self) -> None:
        """Clear all injected context (e.g., on session reset)."""
        self._injected.clear()

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_current_context(self) -> dict:
        """Return working context organised by category."""
        result: dict[str, list[str]] = {}
        for item in self._injected:
            cat = item["category"]
            result.setdefault(cat, []).append(item["content"])
        return result

    def get_relevant_context(self, query: str) -> str:
        """Return the 3 most relevant injected items for a query.

        Uses keyword overlap + recency weighting (no embeddings required).
        """
        if not self._injected:
            return ""
        query_terms = set(query.lower().split())
        scored: list[tuple[float, int, str]] = []
        for idx, item in enumerate(self._injected):
            content = item["content"]
            term_hits = sum(1 for t in query_terms if t in content.lower())
            recency = idx / max(len(self._injected), 1)
            score = term_hits + recency * 0.1
            scored.append((score, idx, content))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return "\n\n".join(c for _, _, c in scored[:3])

    def get_summary_text(self) -> str:
        """Return the background session summary as an injectable string."""
        return self._background.get_summary_text()

    def estimate_tokens(self, history: list[dict]) -> dict:
        """Return token usage breakdown for the current working context."""
        history_text = " ".join(m.get("content", "") for m in history)
        injected_text = " ".join(i["content"] for i in self._injected)
        history_tok = self._counter.count(history_text)
        injected_tok = self._counter.count(injected_text)
        return {
            "history": history_tok,
            "injected": injected_tok,
            "total": history_tok + injected_tok,
        }
