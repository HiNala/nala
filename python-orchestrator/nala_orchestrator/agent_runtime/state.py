"""Durable state model for an agent run.

Each ``/agent`` session produces an ``AgentRun`` that persists inside
``.nala/agent/`` so it survives restarts and can be inspected or resumed.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

log = logging.getLogger("nala.agent_runtime.state")


class AgentPhase(str, Enum):
    IDLE = "idle"
    SCOPING = "scoping"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass
class AgentPlan:
    steps: list[str] = field(default_factory=list)
    risk_summary: str = ""
    scope_description: str = ""
    verification_commands: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = ["## Plan"]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"{i}. {step}")
        if self.risk_summary:
            lines.append(f"\n**Risks:** {self.risk_summary}")
        if self.verification_commands:
            lines.append("\n**Verify with:**")
            for cmd in self.verification_commands:
                lines.append(f"  - `{cmd}`")
        return "\n".join(lines)


@dataclass
class AgentVerification:
    ran_at: str = ""
    commands_executed: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    passed: bool | None = None

    def summary(self) -> str:
        status = "passed" if self.passed else ("failed" if self.passed is False else "pending")
        return f"Verification: {status} ({len(self.commands_executed)} checks)"


@dataclass
class AgentRun:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    objective: str = ""
    phase: AgentPhase = AgentPhase.IDLE
    scope: str = ""
    plan: AgentPlan = field(default_factory=AgentPlan)
    verification: AgentVerification = field(default_factory=AgentVerification)
    current_task_id: str = ""
    team_run_active: bool = False
    artifacts: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["phase"] = self.phase.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> AgentRun:
        d = dict(d)
        d["phase"] = AgentPhase(d.get("phase", "idle"))
        plan_raw = d.pop("plan", {})
        verification_raw = d.pop("verification", {})
        run = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        run.plan = AgentPlan(**{
            k: v for k, v in plan_raw.items() if k in AgentPlan.__dataclass_fields__
        })
        run.verification = AgentVerification(**{
            k: v for k, v in verification_raw.items()
            if k in AgentVerification.__dataclass_fields__
        })
        return run

    def status_text(self) -> str:
        lines = [
            f"**Agent Run** `{self.run_id}`",
            f"**Objective:** {self.objective or '(none)'}",
            f"**Phase:** {self.phase.value}",
        ]
        if self.scope:
            lines.append(f"**Scope:** {self.scope}")
        if self.current_task_id:
            lines.append(f"**Task:** {self.current_task_id}")
        if self.team_run_active:
            lines.append("**Team:** running")
        if self.plan.steps:
            lines.append(f"**Plan:** {len(self.plan.steps)} steps")
        if self.artifacts:
            lines.append(f"**Artifacts:** {len(self.artifacts)}")
        return "\n".join(lines)


# ── Persistence ────────────────────────────────────────────────────────────

def _agent_dir(project_root: Path) -> Path:
    d = project_root / ".nala" / "agent"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(project_root: Path, run: AgentRun) -> Path:
    """Persist the current run to disk."""
    run.touch()
    agent_dir = _agent_dir(project_root)
    current = agent_dir / "current_run.json"
    current.write_text(
        json.dumps(run.to_dict(), indent=2),
        encoding="utf-8",
    )
    return current


def load_run(project_root: Path) -> AgentRun | None:
    """Load the most recent run from disk, if any."""
    current = _agent_dir(project_root) / "current_run.json"
    if not current.exists():
        return None
    try:
        data = json.loads(current.read_text(encoding="utf-8"))
        return AgentRun.from_dict(data)
    except Exception as e:
        log.warning("Failed to load agent run: %s", e)
        return None


def clear_run(project_root: Path) -> None:
    """Remove the current run file."""
    current = _agent_dir(project_root) / "current_run.json"
    if current.exists():
        current.unlink()
