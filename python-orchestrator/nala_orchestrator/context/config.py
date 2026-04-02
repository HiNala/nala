"""Compaction threshold configuration.

Thresholds can be overridden in .nala/config.toml under [context].
Defaults are based on research showing quality degrades sharply above ~80%
utilisation.  Claude Code compacts at ~64%; Nala targets a similar sweet spot.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompactionConfig:
    """Configurable thresholds for context window management."""

    # At this utilisation, start watching for good compaction opportunities.
    soft_threshold: float = 0.60

    # At this utilisation, compact at the next natural breakpoint.
    hard_threshold: float = 0.80

    # At this utilisation, compact immediately regardless of timing.
    critical_threshold: float = 0.90

    # Fraction of the model window reserved for the model's own reasoning.
    reserve_buffer: float = 0.10

    # Number of recent conversation turns to keep verbatim after compaction.
    keep_recent_turns: int = 5

    # Minimum turns before compaction is attempted (avoid over-compacting).
    min_turns_before_compact: int = 4

    @classmethod
    def from_dict(cls, data: dict) -> CompactionConfig:
        """Create from a config dictionary (e.g. from config.toml)."""
        return cls(
            soft_threshold=float(data.get("soft_threshold", 0.60)),
            hard_threshold=float(data.get("hard_threshold", 0.80)),
            critical_threshold=float(data.get("critical_threshold", 0.90)),
            reserve_buffer=float(data.get("reserve_buffer", 0.10)),
            keep_recent_turns=int(data.get("keep_recent_turns", 5)),
            min_turns_before_compact=int(data.get("min_turns_before_compact", 4)),
        )

    def level_for(self, utilization_pct: float) -> str:
        """Return 'normal', 'soft', 'hard', or 'critical'."""
        u = utilization_pct / 100.0
        if u >= self.critical_threshold:
            return "critical"
        if u >= self.hard_threshold:
            return "hard"
        if u >= self.soft_threshold:
            return "soft"
        return "normal"
