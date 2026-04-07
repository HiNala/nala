"""Compaction opportunity detector.

Identifies good moments to compact the context window and blocks compaction
during bad moments (mid-edit, active analysis, etc.).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum

from .config import CompactionConfig


class Priority(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


@dataclass
class CompactionOpportunity:
    """Describes a detected compaction opportunity."""
    reason:               str
    priority:             Priority
    current_utilization:  float   # 0.0–100.0
    estimated_savings:    float   # estimated % reduction after compaction
    safe:                 bool    # False = bad timing, do not compact now


class OpportunityDetector:
    """Detects good (and bad) times to compact the context window."""

    # Idle time (seconds) after which compaction becomes attractive.
    _IDLE_THRESHOLD = 30.0

    def __init__(self) -> None:
        self._last_user_activity: float = time.monotonic()
        self._has_pending_edits:  bool  = False
        self._is_analyzing:       bool  = False
        self._is_mid_reasoning:   bool  = False
        self._turn_count:         int   = 0
        self._previous_user_message: str = ""
        self._last_user_message:  str   = ""
        self._subtask_completed:  bool  = False
        self._tool_output_ready:  bool  = False

    # ── State setters (called by orchestrator/cli) ────────────────────────────

    def mark_user_message(self, text: str = "") -> None:
        self._last_user_activity = time.monotonic()
        self._turn_count += 1
        if text:
            self._previous_user_message = self._last_user_message
            self._last_user_message = text

    def mark_assistant_response(self) -> None:
        self._is_mid_reasoning = False
        self._subtask_completed = False

    def mark_subtask_complete(self) -> None:
        self._subtask_completed = True

    def mark_tool_output_processed(self) -> None:
        self._tool_output_ready = True

    def clear_tool_output_processed(self) -> None:
        self._tool_output_ready = False

    def mark_analysis_start(self) -> None:
        self._is_analyzing = True

    def mark_analysis_complete(self) -> None:
        self._is_analyzing = False

    def mark_edit_pending(self) -> None:
        self._has_pending_edits = True

    def mark_edits_applied(self) -> None:
        self._has_pending_edits = False

    def mark_reasoning_start(self) -> None:
        self._is_mid_reasoning = True

    # ── Detection ─────────────────────────────────────────────────────────────

    def evaluate(
        self,
        utilization_pct: float,
        history_len: int,
        min_turns: int = 4,
        config: CompactionConfig | None = None,
        latest_user_message: str = "",
    ) -> CompactionOpportunity | None:
        """Evaluate whether now is a good time to compact.

        Returns None if utilisation is low and no compaction is needed.
        Returns a CompactionOpportunity with safe=False if compaction is needed
        but timing is bad.
        """
        # Below soft threshold — no action needed.
        cfg = config or CompactionConfig()
        soft_pct = cfg.soft_threshold * 100.0
        hard_pct = cfg.hard_threshold * 100.0
        critical_pct = cfg.critical_threshold * 100.0

        if utilization_pct < soft_pct:
            return None

        # Not enough history to benefit from compaction.
        if history_len < min_turns:
            return None

        # Determine urgency.
        if utilization_pct >= critical_pct:
            priority = Priority.CRITICAL
            reason   = f"Context at {utilization_pct:.0f}% — critical, must compact now"
        elif utilization_pct >= hard_pct:
            priority = Priority.HIGH
            reason   = f"Context at {utilization_pct:.0f}% — compact at next break"
        else:
            priority = Priority.MEDIUM
            reason   = f"Context at {utilization_pct:.0f}% — good time to compact"

        latest = latest_user_message or self._last_user_message
        if self._subtask_completed:
            reason = "Sub-task completed — natural breakpoint for compaction"
            priority = max(priority, Priority.HIGH, key=_priority_rank)
        elif self.is_idle:
            reason = f"User idle for {self.idle_seconds:.0f}s — natural breakpoint for compaction"
        elif self._tool_output_ready:
            reason = "Verbose tool output processed — compact summaries are ready"
            priority = max(priority, Priority.HIGH, key=_priority_rank)
        elif latest and self._looks_like_topic_shift(latest):
            reason = "New topic detected — compact before switching focus"

        # Check for bad timing.
        safe = self._is_safe_to_compact(priority)

        # Estimate savings: tool outputs + older history = ~40–60% of total.
        estimated_savings = 60.0 if self._tool_output_ready else 50.0

        return CompactionOpportunity(
            reason=reason,
            priority=priority,
            current_utilization=utilization_pct,
            estimated_savings=estimated_savings,
            safe=safe,
        )

    def should_compact_now(
        self,
        utilization_pct: float,
        history_len: int,
        min_turns: int = 4,
        config: CompactionConfig | None = None,
        latest_user_message: str = "",
    ) -> bool:
        """True if compaction should proceed immediately."""
        opp = self.evaluate(
            utilization_pct,
            history_len,
            min_turns,
            config=config,
            latest_user_message=latest_user_message,
        )
        if opp is None:
            return False
        if opp.priority == Priority.CRITICAL:
            return True   # critical overrides bad timing
        return opp.safe

    # ── Internal ──────────────────────────────────────────────────────────────

    def _is_safe_to_compact(self, priority: Priority) -> bool:
        """Return True when timing is acceptable for compaction."""
        # Critical always overrides.
        if priority == Priority.CRITICAL:
            return True

        # Never compact during active multi-file edits.
        if self._has_pending_edits:
            return False

        # Never compact during an active analysis run.
        if self._is_analyzing:
            return False

        # Never compact mid-reasoning.
        if self._is_mid_reasoning:
            return False

        return True

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_user_activity

    @property
    def is_idle(self) -> bool:
        return self.idle_seconds >= self._IDLE_THRESHOLD

    def _looks_like_topic_shift(self, latest_user_message: str) -> bool:
        previous = _keyword_set(self._previous_user_message)
        current = _keyword_set(latest_user_message)
        if not previous or not current:
            return False
        overlap = len(previous & current)
        return overlap == 0


def _priority_rank(priority: Priority) -> int:
    order = {
        Priority.LOW: 0,
        Priority.MEDIUM: 1,
        Priority.HIGH: 2,
        Priority.CRITICAL: 3,
    }
    return order[priority]


def _keyword_set(text: str) -> set[str]:
    words = {
        w for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())
        if w not in {"the", "and", "for", "with", "this", "that", "from", "into"}
    }
    return words
