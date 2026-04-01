"""Task decomposer.

Takes a high-level objective and breaks it into independent sub-tasks
with clear boundaries, dependency ordering, and file scope.

Uses the code graph (if available) to find natural module boundaries.
Falls back to directory-based decomposition when the graph is absent.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class SubTask:
    """One unit of decomposed work."""
    title: str
    objective: str
    scope: list[str]          # file or directory paths
    wave: int = 0             # 0 = first wave, higher = later
    dependencies: list[str] = field(default_factory=list)  # SubTask titles
    read_only: bool = True


@dataclass
class TaskPlan:
    """A complete decomposition of a high-level objective into waves."""
    objective: str
    waves: list[list[SubTask]]

    @property
    def all_tasks(self) -> list[SubTask]:
        return [t for wave in self.waves for t in wave]

    def summary(self) -> str:
        lines = [f"Task plan for: {self.objective[:80]}"]
        for i, wave in enumerate(self.waves):
            lines.append(f"\n  Wave {i + 1} ({len(wave)} tasks, parallel):")
            for task in wave:
                ro = " [read-only]" if task.read_only else " [read-write]"
                scope = ", ".join(task.scope[:2]) or "project"
                lines.append(f"    - {task.title}: {scope}{ro}")
        return "\n".join(lines)


class TaskDecomposer:
    """Decomposes objectives into parallelisable task waves."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def decompose(
        self,
        objective: str,
        read_only: bool = False,
        max_tasks: int = 8,
    ) -> TaskPlan:
        """Decompose objective into waves using directory structure."""
        objective_lower = objective.lower()

        # Detect intent
        is_analysis = any(kw in objective_lower for kw in
                          ("analyze", "analyse", "check", "review", "scan", "find"))
        is_fix = any(kw in objective_lower for kw in
                     ("fix", "refactor", "improve", "update", "change"))

        modules = self._discover_modules(max_tasks)

        if is_analysis and not is_fix:
            # All analysis tasks can run in parallel (Wave 1 only)
            wave1 = [
                SubTask(
                    title=f"Analyze {m}",
                    objective=f"{objective} in {m}",
                    scope=[m],
                    wave=0,
                    read_only=True,
                )
                for m in modules
            ]
            return TaskPlan(objective=objective, waves=[wave1])

        # For mixed or fix tasks: analyse first, then fix
        wave1 = [
            SubTask(
                title=f"Analyze {m}",
                objective=f"Identify issues in {m}: {objective}",
                scope=[m],
                wave=0,
                read_only=True,
            )
            for m in modules
        ]
        wave2 = [
            SubTask(
                title=f"Fix {m}",
                objective=f"Apply fixes in {m}: {objective}",
                scope=[m],
                wave=1,
                dependencies=[f"Analyze {m}"],
                read_only=read_only,
            )
            for m in modules
        ]
        wave3 = [
            SubTask(
                title="Synthesize results",
                objective="Review all changes and write a summary report",
                scope=[],
                wave=2,
                dependencies=[t.title for t in wave2],
                read_only=True,
            )
        ]
        return TaskPlan(objective=objective, waves=[wave1, wave2, wave3])

    def _discover_modules(self, max_modules: int) -> list[str]:
        """Discover top-level modules/directories to use as task scopes."""
        modules: list[str] = []
        # Python source
        for src_dir in ["src", "lib", "python-orchestrator", "."]:
            candidate = self._root / src_dir
            if not candidate.exists():
                continue
            for item in sorted(candidate.iterdir()):
                if item.is_dir() and not item.name.startswith((".", "_", "target")):
                    rel = str(item.relative_to(self._root))
                    modules.append(rel)
                    if len(modules) >= max_modules:
                        return modules
            if modules:
                return modules
        return ["."]  # fallback: entire project
