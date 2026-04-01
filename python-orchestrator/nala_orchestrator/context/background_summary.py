"""Background summary builder.

Maintains a running, always-ready summary of the current session.  Updated
after every few turns so that compaction is instant — the system swaps the
full history for this pre-built summary plus the most recent turns.

The summary captures:
  - Session objective (what the user is trying to accomplish)
  - Work completed so far
  - Current state (active files / task)
  - Key decisions and constraints
  - Next steps
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# Rebuild every N turns (balance between freshness and LLM cost).
_UPDATE_INTERVAL = 3


@dataclass
class SessionSummary:
    """Structured summary of a session up to the current point."""
    objective:    str = ""
    completed:    list[str] = field(default_factory=list)
    current_task: str = ""
    decisions:    list[str] = field(default_factory=list)
    next_steps:   list[str] = field(default_factory=list)
    turn_count:   int = 0
    updated_at:   float = field(default_factory=time.monotonic)

    def to_text(self) -> str:
        """Format the summary as a compact context-injection string."""
        parts = ["[SESSION SUMMARY]"]
        if self.objective:
            parts.append(f"Objective: {self.objective}")
        if self.completed:
            parts.append("Completed:")
            parts.extend(f"  - {item}" for item in self.completed[-10:])
        if self.current_task:
            parts.append(f"Current task: {self.current_task}")
        if self.decisions:
            parts.append("Key decisions:")
            parts.extend(f"  - {d}" for d in self.decisions[-5:])
        if self.next_steps:
            parts.append("Next steps:")
            parts.extend(f"  - {s}" for s in self.next_steps[-5:])
        parts.append("[END SUMMARY]")
        return "\n".join(parts)

    def is_empty(self) -> bool:
        return not (self.objective or self.completed or self.current_task)


class BackgroundSummary:
    """Maintains an always-ready session summary, updated periodically."""

    def __init__(self) -> None:
        self._summary: Optional[SessionSummary] = None
        self._turn_since_update: int = 0
        self._history_snapshot: list[dict] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def on_turn(self, history: list[dict]) -> None:
        """Called after each conversation turn.  Rebuilds if stale."""
        self._turn_since_update += 1
        if self._turn_since_update >= _UPDATE_INTERVAL:
            self._rebuild(history)
            self._turn_since_update = 0

    def get_summary(self) -> Optional[SessionSummary]:
        """Return the current summary (may be None if not yet built)."""
        return self._summary

    def get_summary_text(self) -> str:
        """Return the summary as an injectable context string."""
        if self._summary and not self._summary.is_empty():
            return self._summary.to_text()
        return "(no session summary yet)"

    def force_rebuild(self, history: list[dict]) -> SessionSummary:
        """Force an immediate rebuild regardless of update interval."""
        self._rebuild(history)
        self._turn_since_update = 0
        return self._summary  # type: ignore[return-value]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild(self, history: list[dict]) -> None:
        """Heuristically extract a structured summary from conversation history."""
        if not history:
            self._summary = SessionSummary()
            return

        user_messages  = [m["content"] for m in history if m.get("role") == "user"]
        asst_messages  = [m["content"] for m in history if m.get("role") == "assistant"]

        # Objective: first user message (usually states the goal).
        objective = user_messages[0][:200].replace("\n", " ") if user_messages else ""

        # Current task: most recent user message.
        current_task = user_messages[-1][:200].replace("\n", " ") if user_messages else ""

        # Completed work: extract action-like phrases from assistant messages.
        completed: list[str] = []
        for msg in asst_messages:
            for line in msg.splitlines():
                line = line.strip()
                if any(line.lower().startswith(kw) for kw in
                       ("applied", "created", "edited", "refactored", "fixed",
                        "added", "removed", "updated", "changed")):
                    completed.append(line[:120])
                    if len(completed) >= 10:
                        break

        # Key decisions: lines starting with "decided", "using", "chose", etc.
        decisions: list[str] = []
        for msg in asst_messages:
            for line in msg.splitlines():
                line = line.strip()
                if any(line.lower().startswith(kw) for kw in
                       ("decided", "using ", "chose ", "will use", "approach:")):
                    decisions.append(line[:120])
                    if len(decisions) >= 5:
                        break

        # Next steps: lines starting with "next", "todo", "still need", etc.
        next_steps: list[str] = []
        if asst_messages:
            last_asst = asst_messages[-1]
            for line in last_asst.splitlines():
                line = line.strip()
                if any(line.lower().startswith(kw) for kw in
                       ("next", "todo", "still need", "should", "need to")):
                    next_steps.append(line[:120])
                    if len(next_steps) >= 5:
                        break

        self._summary = SessionSummary(
            objective=objective,
            completed=completed,
            current_task=current_task,
            decisions=decisions,
            next_steps=next_steps,
            turn_count=len(history),
            updated_at=time.monotonic(),
        )
        log.debug(
            "BackgroundSummary rebuilt: %d turns, %d completed, %d decisions",
            len(history), len(completed), len(decisions),
        )
