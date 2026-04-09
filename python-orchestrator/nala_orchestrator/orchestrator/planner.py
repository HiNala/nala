"""Mission 32: Task planner — builds wave-structured execution plans.

Converts a ClassifiedTask into an ExecutionPlan with ordered waves of
parallel AgentTasks. The plan is presented to the user for approval before
any sub-agents are launched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .classifier import ClassifiedTask

# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class AgentTask:
    task_id: str
    specialist_type: str      # "security" | "refactor" | "tester" | "reviewer" | "general"
    mission: str
    system_prompt_additions: str = ""
    scope: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    output_format: str = "findings"   # "findings" | "diff" | "report" | "tests"
    timeout_seconds: int = 180

    @classmethod
    def make(cls, specialist: str, mission: str, scope: list[str],
             output_format: str = "findings", timeout: int = 180) -> AgentTask:
        return cls(
            task_id=f"{specialist}-{uuid.uuid4().hex[:6]}",
            specialist_type=specialist,
            mission=mission,
            scope=scope,
            output_format=output_format,
            timeout_seconds=timeout,
        )


@dataclass
class Wave:
    wave_number: int
    description: str
    tasks: list[AgentTask]
    depends_on: int | None = None   # Wave number this wave must follow
    parallel: bool = True


@dataclass
class ExecutionPlan:
    objective: str
    waves: list[Wave]
    estimated_duration: str = "~1 minute"
    estimated_token_cost: int = 50_000
    requires_user_approval: bool = True

    @property
    def total_tasks(self) -> int:
        return sum(len(w.tasks) for w in self.waves)

    def summary(self) -> str:
        lines = [f"Plan for: {self.objective[:80]}"]
        for wave in self.waves:
            mode = "parallel" if wave.parallel else "sequential"
            lines.append(f"\n  Wave {wave.wave_number} — {wave.description} ({mode}):")
            for task in wave.tasks:
                scope_str = ", ".join(task.scope[:2]) or "project"
                lines.append(f"    • {task.specialist_type}: {task.mission[:60]} [{scope_str}]")
        lines.append(
            f"\n  Estimated: {len(self.waves)} waves, {self.total_tasks} agents, "
            f"{self.estimated_duration}"
        )
        return "\n".join(lines)


# ── Planner ────────────────────────────────────────────────────────────────

class TaskPlanner:
    """Creates structured execution plans from classified tasks."""

    def plan(
        self,
        task: ClassifiedTask,
        project_root: Path | None = None,
    ) -> ExecutionPlan:
        scope = task.targets or (
            [str(project_root)] if project_root else ["."]
        )
        intent = task.intent
        complexity = task.complexity

        if complexity == "full_codebase":
            return self._plan_full_codebase(task.intent, scope)
        if complexity == "multi_file":
            return self._plan_multi_file(intent, scope)
        # Should not be called for simple/single_file — but handle gracefully
        return self._plan_single(intent, scope)

    # ── Wave templates ─────────────────────────────────────────────────────

    def _plan_full_codebase(self, intent: str, scope: list[str]) -> ExecutionPlan:
        waves: list[Wave] = []

        # Wave 1: analysis
        analysis_tasks = [
            AgentTask.make("security", "Scan for vulnerabilities and hardcoded secrets", scope),
            AgentTask.make("reviewer", "Identify complexity hotspots and code smells", scope),
            AgentTask.make("general", "Map dependency structure and coupling", scope, output_format="report"),
        ]
        waves.append(Wave(1, "Analysis (parallel)", analysis_tasks, parallel=True))

        if intent in {"fix", "refactor"}:
            fix_tasks = [
                AgentTask.make("refactor", "Refactor high-complexity functions", scope, output_format="diff"),
                AgentTask.make("security", "Remediate security findings from Wave 1", scope, output_format="diff"),
            ]
            waves.append(Wave(2, "Fixes (parallel)", fix_tasks, depends_on=1, parallel=True))
            verify_tasks = [
                AgentTask.make("tester", "Write tests covering changed code", scope, output_format="tests"),
                AgentTask.make("reviewer", "Final review of all changes", scope, output_format="report"),
            ]
            waves.append(Wave(3, "Verification (sequential)", verify_tasks, depends_on=2, parallel=False))
            duration = "~3 minutes"
            cost = 150_000
        else:
            duration = "~1 minute"
            cost = 60_000

        return ExecutionPlan(
            objective=f"Full-codebase {intent}",
            waves=waves,
            estimated_duration=duration,
            estimated_token_cost=cost,
        )

    def _plan_multi_file(self, intent: str, scope: list[str]) -> ExecutionPlan:
        waves: list[Wave] = []
        scope_str = ", ".join(scope[:2])

        if intent == "review":
            tasks = [
                AgentTask.make("security", f"Security audit of {scope_str}", scope),
                AgentTask.make("reviewer", f"Code quality review of {scope_str}", scope),
            ]
            waves.append(Wave(1, "Review (parallel)", tasks, parallel=True))
            duration = "~30 seconds"
            cost = 30_000

        elif intent in {"fix", "refactor"}:
            analysis = [
                AgentTask.make("reviewer", f"Identify issues in {scope_str}", scope),
            ]
            waves.append(Wave(1, "Analysis", analysis, parallel=False))
            fixes = [
                AgentTask.make("refactor", f"Fix issues found in {scope_str}", scope, output_format="diff"),
            ]
            waves.append(Wave(2, "Fixes", fixes, depends_on=1, parallel=False))
            duration = "~1 minute"
            cost = 40_000

        elif intent == "test":
            tasks = [
                AgentTask.make("tester", f"Write tests for {scope_str}", scope, output_format="tests"),
            ]
            waves.append(Wave(1, "Test generation", tasks, parallel=False))
            duration = "~30 seconds"
            cost = 20_000

        else:
            tasks = [
                AgentTask.make("general", f"Analyze {scope_str}: {intent}", scope),
            ]
            waves.append(Wave(1, "Analysis", tasks, parallel=False))
            duration = "~20 seconds"
            cost = 15_000

        return ExecutionPlan(
            objective=f"{intent.title()} {scope_str}",
            waves=waves,
            estimated_duration=duration,
            estimated_token_cost=cost,
            requires_user_approval=intent in {"fix", "refactor"},
        )

    def _plan_single(self, intent: str, scope: list[str]) -> ExecutionPlan:
        tasks = [AgentTask.make("general", f"{intent}: {scope[0] if scope else 'file'}", scope)]
        return ExecutionPlan(
            objective=f"{intent.title()} {scope[0] if scope else 'file'}",
            waves=[Wave(1, intent.title(), tasks, parallel=False)],
            estimated_duration="~15 seconds",
            estimated_token_cost=10_000,
            requires_user_approval=False,
        )
