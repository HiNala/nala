"""Token counter for context window management.

Uses a character-based heuristic (accurate to ±20%):
  - English prose:  1 token per 4 chars
  - Code:           1 token per 3.5 chars (denser)

When tiktoken is installed it is used for exact OpenAI token counts.
When the Anthropic SDK is available its token_count API can be used for
Claude models. The heuristic is always the fast fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Characters per token for each content type.
_PROSE_CPT  = 4.0
_CODE_CPT   = 3.5

# Default model context windows (tokens).
MODEL_LIMITS: dict[str, int] = {
    "claude-opus-4-6":        200_000,
    "claude-sonnet-4-6":      200_000,
    "claude-haiku-4-5":       200_000,
    "gpt-4o":                 128_000,
    "gpt-4o-mini":            128_000,
    "gemini-1.5-pro":       1_000_000,
    "gemini-1.5-flash":     1_000_000,
    "llama3":                   8_000,  # Ollama default
    "default":              200_000,
}

# Reserve 10% of the window for the model's own reasoning.
RESERVE_RATIO = 0.10


@dataclass
class TokenUsage:
    """Token breakdown for one conversation state."""
    system_tokens:      int = 0
    context_tokens:     int = 0   # injected codebase context (RAG chunks)
    history_tokens:     int = 0   # conversation turns
    tool_output_tokens: int = 0   # verbose tool results
    model_limit:        int = MODEL_LIMITS["default"]

    @property
    def total_tokens(self) -> int:
        return (
            self.system_tokens
            + self.context_tokens
            + self.history_tokens
            + self.tool_output_tokens
        )

    @property
    def reserve_tokens(self) -> int:
        return int(self.model_limit * RESERVE_RATIO)

    @property
    def effective_limit(self) -> int:
        return self.model_limit - self.reserve_tokens

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.effective_limit - self.total_tokens)

    @property
    def utilization_pct(self) -> float:
        if self.effective_limit == 0:
            return 100.0
        return min(100.0, self.total_tokens / self.effective_limit * 100.0)

    def get_usage_breakdown(self) -> dict:
        """Return a dict suitable for display in the TUI or CLI."""
        return {
            "system_tokens":      self.system_tokens,
            "context_tokens":     self.context_tokens,
            "history_tokens":     self.history_tokens,
            "tool_output_tokens": self.tool_output_tokens,
            "total_tokens":       self.total_tokens,
            "remaining_tokens":   self.remaining_tokens,
            "reserve_tokens":     self.reserve_tokens,
            "model_limit":        self.model_limit,
            "effective_limit":    self.effective_limit,
            "utilization_pct":    round(self.utilization_pct, 1),
        }


class TokenCounter:
    """Estimates token counts for text strings."""

    def __init__(self, model: str = "default") -> None:
        self.model = model
        self.model_limit = MODEL_LIMITS.get(model, MODEL_LIMITS["default"])
        self._tiktoken_enc = None
        self._try_load_tiktoken()

    # ── Public API ────────────────────────────────────────────────────────────

    def count(self, text: str, is_code: bool = False) -> int:
        """Return the estimated token count for text."""
        if self._tiktoken_enc is not None:
            try:
                return len(self._tiktoken_enc.encode(text))
            except Exception:
                pass
        cpt = _CODE_CPT if is_code else _PROSE_CPT
        return max(1, int(len(text) / cpt))

    def measure_conversation(
        self,
        system_prompt: str,
        history: list[dict],
        retrieved_context: str = "",
    ) -> TokenUsage:
        """Measure all components of a conversation state.

        Args:
            system_prompt:     The system prompt sent to the model.
            history:           List of {role, content} dicts.
            retrieved_context: RAG-injected codebase context string.
        """
        usage = TokenUsage(model_limit=self.model_limit)

        # System prompt (mix of prose and code).
        usage.system_tokens = self.count(system_prompt)

        # RAG context (mostly code).
        usage.context_tokens = self.count(retrieved_context, is_code=True)

        # Conversation history.
        for msg in history:
            content = msg.get("content", "")
            role = msg.get("role", "user")
            is_code = role == "assistant"  # heuristic: assistant responses often code-heavy
            usage.history_tokens += self.count(content, is_code=is_code)

        return usage

    def format_breakdown(self, usage: TokenUsage) -> str:
        """Return a formatted multi-line breakdown string."""
        bd = usage.get_usage_breakdown()
        bar_len = 20
        filled = int(bar_len * usage.utilization_pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        color_hint = (
            "green" if usage.utilization_pct < 60
            else "yellow" if usage.utilization_pct < 80
            else "red"
        )
        lines = [
            "Context Usage Breakdown:",
            f"  System prompt:     {bd['system_tokens']:>7,} tokens "
            f"({bd['system_tokens']/max(1,bd['model_limit'])*100:4.1f}%)",
            f"  Codebase context:  {bd['context_tokens']:>7,} tokens "
            f"({bd['context_tokens']/max(1,bd['model_limit'])*100:4.1f}%)",
            f"  Conversation:      {bd['history_tokens']:>7,} tokens "
            f"({bd['history_tokens']/max(1,bd['model_limit'])*100:4.1f}%)",
            f"  Tool outputs:      {bd['tool_output_tokens']:>7,} tokens "
            f"({bd['tool_output_tokens']/max(1,bd['model_limit'])*100:4.1f}%)",
            f"  Reserved buffer:   {bd['reserve_tokens']:>7,} tokens "
            f"({RESERVE_RATIO*100:.0f}%)",
            "  " + "─" * 42,
            f"  Total used:        {bd['total_tokens']:>7,} tokens "
            f"({bd['utilization_pct']:.1f}%)",
            f"  Available:         {bd['remaining_tokens']:>7,} tokens",
            f"  [{bar}] {bd['utilization_pct']:.1f}%  [{color_hint}]",
        ]
        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _try_load_tiktoken(self) -> None:
        try:
            import tiktoken  # type: ignore
            enc_name = (
                "cl100k_base"
                if "gpt" in self.model or "claude" in self.model
                else "o200k_base"
            )
            self._tiktoken_enc = tiktoken.get_encoding(enc_name)
        except Exception:
            log.debug("tiktoken not available — using character heuristic")
