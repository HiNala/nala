"""Handoff document schema.

Defines the structured data that captures session state for seamless
continuity across compaction and session boundaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class InProgressState:
    """What the agent was actively doing when the handoff was created."""
    current_task: str = ""
    current_file: str = ""
    current_function: str = ""
    pending_changes: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.current_task or self.current_file)


@dataclass
class ModifiedFile:
    """A file that was touched during the session."""
    path: str
    change_summary: str = ""
    is_saved: bool = True
    has_tests: bool = False


@dataclass
class Decision:
    """An architectural or technical decision made during the session."""
    text: str
    rationale: str = ""
    affected_files: list[str] = field(default_factory=list)


@dataclass
class HandoffDocument:
    """Complete handoff state for a session or compaction point."""
    timestamp: str
    session_id: str
    trigger: str                   # "compaction" | "session_end" | "manual" | "threshold"
    objective: str = ""
    completed_actions: list[str] = field(default_factory=list)
    in_progress: InProgressState = field(default_factory=InProgressState)
    modified_files: list[ModifiedFile] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    critical_context: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, session_id: str, trigger: str) -> "HandoffDocument":
        return cls(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            trigger=trigger,
        )

    def to_json(self) -> str:
        """Serialise to JSON string."""
        def _asdict(obj) -> object:
            if isinstance(obj, (HandoffDocument, InProgressState,
                                ModifiedFile, Decision)):
                return {k: _asdict(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [_asdict(i) for i in obj]
            return obj
        return json.dumps(_asdict(self), indent=2)

    def to_markdown(self) -> str:
        """Render as a human-readable markdown document (<2 000 tokens)."""
        ts = self.timestamp[:16].replace("T", " ")
        lines = [
            f"# Handoff: {self.session_id}",
            f"*Created: {ts} | Trigger: {self.trigger}*",
            "",
        ]
        if self.objective:
            lines += ["## Objective", self.objective, ""]
        if self.completed_actions:
            lines += ["## Completed"]
            lines += [f"- {a}" for a in self.completed_actions]
            lines += [""]
        if not self.in_progress.is_empty():
            lines += ["## In Progress"]
            if self.in_progress.current_task:
                lines += [f"**Task**: {self.in_progress.current_task}"]
            if self.in_progress.current_file:
                lines += [f"**File**: `{self.in_progress.current_file}`"]
            if self.in_progress.current_function:
                lines += [f"**Function**: `{self.in_progress.current_function}`"]
            if self.in_progress.pending_changes:
                lines += ["**Pending**:"]
                lines += [f"  - {c}" for c in self.in_progress.pending_changes]
            if self.in_progress.blocking_issues:
                lines += ["**Blockers**:"]
                lines += [f"  - {b}" for b in self.in_progress.blocking_issues]
            lines += [""]
        if self.modified_files:
            lines += ["## Modified Files"]
            for mf in self.modified_files:
                saved = "saved" if mf.is_saved else "UNSAVED"
                lines += [f"- `{mf.path}` ({saved}): {mf.change_summary}"]
            lines += [""]
        if self.decisions:
            lines += ["## Key Decisions"]
            for d in self.decisions:
                lines += [f"- {d.text}"]
                if d.rationale:
                    lines += [f"  *Rationale: {d.rationale}*"]
            lines += [""]
        if self.next_steps:
            lines += ["## Next Steps"]
            lines += [f"- {s}" for s in self.next_steps]
            lines += [""]
        if self.critical_context:
            lines += ["## Critical Context"]
            lines += [f"- {c}" for c in self.critical_context]
            lines += [""]
        if self.constraints:
            lines += ["## Constraints / Don't Do"]
            lines += [f"- {c}" for c in self.constraints]
            lines += [""]
        return "\n".join(lines)

    def token_estimate(self) -> int:
        """Rough token count for budget checking."""
        return len(self.to_markdown()) // 4

    def validate(self) -> list[str]:
        """Return a list of validation warnings."""
        warnings: list[str] = []
        if not self.objective:
            warnings.append("Missing objective")
        if not self.completed_actions and self.in_progress.is_empty():
            warnings.append("No completed actions or in-progress state")
        if self.token_estimate() > 3_000:
            warnings.append(f"Handoff may be too large (~{self.token_estimate()} tokens)")
        return warnings
