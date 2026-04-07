"""Context compaction engine.

Three-tier compaction strategy (applied in order):

  Tier 1 — Tool output pruning (highest savings, lowest loss)
    Replace verbose tool outputs with 2-3 line summaries.
    Recovers 30-50% of consumed tokens.

  Tier 2 — Conversation summarisation (moderate savings)
    Summarise older turns into structured key-decisions format.
    Keep the most recent N turns verbatim.

  Tier 3 — Context re-injection hint (used after compaction)
    Return a note indicating which topics should be re-injected
    at the next query based on the current session focus.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ..compression.pipeline import CompressionPipeline

log = logging.getLogger(__name__)

# Patterns that indicate a turn contains verbose tool output.
_TOOL_INDICATORS = [
    "```", "---", "def ", "fn ", "class ", "import ",
    "function ", "// ", "# ", "/*",
]

_MAX_TOOL_LINES = 30   # lines above this threshold → prune


@dataclass
class CompactionResult:
    """Outcome of a compaction operation."""
    original_turns:   int
    compacted_turns:  int
    tokens_before:    int
    tokens_after:     int
    strategy_used:    str   # "tier1", "tier2", "tier1+tier2"
    summary:          str   # human-readable compaction summary


class Compactor:
    """Performs context window compaction when triggered by the detector."""

    def __init__(self, keep_recent: int = 5) -> None:
        self._keep_recent = keep_recent

    def compact(
        self,
        history: list[dict],
        token_estimate_fn=None,
        focus: str = "",
    ) -> tuple[list[dict], CompactionResult]:
        """Compact the conversation history.

        Args:
            history:            List of {role, content} dicts.
            token_estimate_fn:  Optional callable(text) -> int.

        Returns:
            (new_history, CompactionResult)
        """
        if not history:
            return history, CompactionResult(
                original_turns=0, compacted_turns=0,
                tokens_before=0, tokens_after=0,
                strategy_used="none", summary="Nothing to compact."
            )

        def _tok(text: str) -> int:
            if token_estimate_fn:
                return token_estimate_fn(text)
            return len(text) // 4

        def _content_str(m: dict) -> str:
            c = m.get("content", "")
            if isinstance(c, list):
                # Anthropic-style content blocks (tool_use / tool_result)
                return " ".join(
                    block.get("content", "") or block.get("text", "")
                    for block in c if isinstance(block, dict)
                )
            return str(c) if c else ""

        tokens_before = sum(_tok(_content_str(m)) for m in history)

        # Split history into old (to compact) and recent (to keep verbatim).
        if len(history) <= self._keep_recent:
            recent = history
            old = []
        else:
            old = history[: len(history) - self._keep_recent]
            recent = history[len(history) - self._keep_recent :]

        # ── Tier 1: compression pipeline (dedup + tool outputs + code + prose)
        pipeline = CompressionPipeline()
        pruned_old_with_recent, pipe_report = pipeline.compress_history(
            history, keep_recent=self._keep_recent
        )
        # Extract only the old portion (pipeline keeps recent at end)
        pruned_old = pruned_old_with_recent[: len(pruned_old_with_recent) - len(recent)]
        tier1_applied = bool(pipe_report.stages_applied)

        # ── Tier 2: summarise old turns into one system block ─────────────
        tier2_applied = False
        preserved_focus_turns: list[dict] = []
        if focus and pruned_old:
            preserved_focus_turns = self._select_focus_turns(pruned_old, focus)
            if preserved_focus_turns:
                preserved_ids = {id(m) for m in preserved_focus_turns}
                pruned_old = [m for m in pruned_old if id(m) not in preserved_ids]

        if pruned_old:
            summary_text = self._summarise_turns(pruned_old)
            compacted_history = [
                {"role": "system", "content": summary_text}
            ] + preserved_focus_turns + recent
            tier2_applied = True
        else:
            compacted_history = preserved_focus_turns + recent

        tokens_after = sum(_tok(_content_str(m)) for m in compacted_history)

        strategies = []
        if tier1_applied:
            strategies.append("tier1[" + "+".join(pipe_report.stages_applied) + "]")
        if tier2_applied:
            strategies.append("tier2")
        strategy_used = "+".join(strategies) if strategies else "none"

        saved = tokens_before - tokens_after
        preserved_summary = ""
        if preserved_focus_turns:
            preserved_summary = (
                f"Preserved {len(preserved_focus_turns)} focus-relevant turns. "
            )
        summary = (
            f"Compacted {len(old)} older turns → 1 summary block. "
            f"{preserved_summary}"
            f"Kept {len(recent)} recent turns verbatim. "
            f"Estimated savings: ~{saved:,} tokens. "
            f"Pipeline: {pipe_report.reduction_pct:.0f}% content reduction."
        )

        return compacted_history, CompactionResult(
            original_turns=len(history),
            compacted_turns=len(compacted_history),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            strategy_used=strategy_used,
            summary=summary,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _is_verbose_tool_output(content: str) -> bool:
        lines = content.splitlines()
        if len(lines) < _MAX_TOOL_LINES:
            return False
        code_lines = sum(
            1 for line in lines
            if any(line.lstrip().startswith(ind) for ind in _TOOL_INDICATORS)
        )
        return code_lines > len(lines) * 0.4

    @staticmethod
    def _prune_tool_output(content: str) -> str:
        lines = content.splitlines()
        head = lines[:3]
        tail = lines[-3:]
        omitted = len(lines) - 6
        if omitted <= 0:
            return content
        return "\n".join(head) + f"\n... [{omitted} lines omitted] ...\n" + "\n".join(tail)

    @staticmethod
    def _summarise_turns(turns: list[dict]) -> str:
        """Produce a structured summary of older turns.

        Handles all message roles that appear in the tool-calling loop:
        - "user"      — developer queries
        - "assistant" — model replies and tool invocations
        - "tool"      — tool execution results (the actual work done)
        """
        import json as _json

        user_msgs  = [m["content"] for m in turns if m.get("role") == "user"
                      and isinstance(m.get("content"), str)]
        asst_msgs  = [m["content"] for m in turns if m.get("role") == "assistant"
                      and isinstance(m.get("content"), str) and m.get("content")]

        # Extract tool calls made by the assistant (stored as list in content or tool_calls)
        tool_calls_made: list[str] = []
        for m in turns:
            if m.get("role") == "assistant":
                for tc in m.get("tool_calls", []):
                    fn = tc.get("function", {})
                    name = fn.get("name", "?")
                    try:
                        args = _json.loads(fn.get("arguments", "{}"))
                        # Show the most meaningful arg (path, command, query, pattern)
                        key_arg = (
                            args.get("path") or args.get("command") or
                            args.get("query") or args.get("pattern") or
                            next(iter(args.values()), "")
                        )
                        tool_calls_made.append(f"{name}({str(key_arg)[:60]})")
                    except Exception:
                        tool_calls_made.append(name)

        # Extract significant tool results (role="tool")
        tool_results: list[str] = []
        for m in turns:
            if m.get("role") == "tool":
                content = str(m.get("content", ""))
                first_line = content.splitlines()[0] if content else ""
                if first_line and not first_line.startswith("("):
                    tool_results.append(first_line[:100])

        user_summary = (
            " | ".join(m[:120].replace("\n", " ") for m in user_msgs[-5:])
            or "(none)"
        )
        asst_summary = (
            " | ".join(m[:150].replace("\n", " ") for m in asst_msgs[-3:])
            or "(none)"
        )

        parts = [
            "[COMPACTED CONTEXT — earlier conversation summary]",
            f"User asked about: {user_summary}",
            f"Assistant covered: {asst_summary}",
        ]
        if tool_calls_made:
            parts.append(f"Tools used: {', '.join(tool_calls_made[-8:])}")
        if tool_results:
            parts.append(f"Key tool outputs: {' | '.join(tool_results[-4:])}")
        parts.append("[End of compacted context — recent turns follow]")
        return "\n".join(parts)

    @staticmethod
    def _select_focus_turns(turns: list[dict], focus: str, limit: int = 2) -> list[dict]:
        focus_terms = {
            term for term in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", focus.lower())
            if term not in {"focus", "preserve", "module", "refactor", "the", "and", "for"}
        }
        if not focus_terms:
            return []
        scored: list[tuple[int, int, dict]] = []
        for idx, turn in enumerate(turns):
            content = str(turn.get("content", "")).lower()
            score = sum(1 for term in focus_terms if term in content)
            if score > 0:
                scored.append((score, idx, turn))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        selected = scored[:limit]
        selected.sort(key=lambda item: item[1])
        return [turn for _, _, turn in selected]
