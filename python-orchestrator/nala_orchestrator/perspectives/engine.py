"""
Perspectives engine.

Orchestrates all analysis perspectives. Callers pass a project root;
the engine runs every applicable perspective (skipping those that require
Neo4j when the graph is unavailable) and returns a combined list of
PerspectiveResult objects.

Usage:
    engine = PerspectivesEngine(config, graph=graph_conn)
    results = await engine.run_all(project_root)
    results = await engine.run_one("security", project_root)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

from .base import BasePerspective, PerspectiveResult
from .complexity import ComplexityPerspective
from .dead_code import DeadCodePerspective
from .dependency import DependencyPerspective
from .duplication import DuplicationPerspective
from .security import SecurityPerspective
from .test_coverage import TestCoveragePerspective

if TYPE_CHECKING:
    from nala_orchestrator.config import Config
    from nala_orchestrator.graph.connection import GraphConnection

log = logging.getLogger(__name__)


class PerspectivesEngine:
    """Runs analysis perspectives and aggregates findings."""

    def __init__(
        self,
        config: "Config",
        graph: Optional["GraphConnection"] = None,
    ) -> None:
        self.config = config
        self.graph = graph
        self._perspectives: list[BasePerspective] = [
            ComplexityPerspective(config, graph),
            SecurityPerspective(config, graph),
            DuplicationPerspective(config, graph),
            TestCoveragePerspective(config, graph),
            DeadCodePerspective(config, graph),
            DependencyPerspective(config, graph),
        ]

    # ── Public API ─────────────────────────────────────────────────────────

    async def run_all(self, project_root: str) -> list[PerspectiveResult]:
        """Run every applicable perspective and return results."""
        tasks = [
            self._run_safe(p, project_root)
            for p in self._perspectives
            if self._should_run(p)
        ]
        return await asyncio.gather(*tasks)

    async def run_one(
        self, name: str, project_root: str
    ) -> Optional[PerspectiveResult]:
        """Run a single perspective by name."""
        for p in self._perspectives:
            if p.name == name:
                if not self._should_run(p):
                    return PerspectiveResult(
                        perspective_name=name,
                        summary=f"Perspective '{name}' requires Neo4j (not available).",
                    )
                return await self._run_safe(p, project_root)
        return None

    def perspective_names(self) -> list[str]:
        return [p.name for p in self._perspectives]

    def available_names(self) -> list[str]:
        return [p.name for p in self._perspectives if self._should_run(p)]

    # ── Helpers ────────────────────────────────────────────────────────────

    def _should_run(self, perspective: BasePerspective) -> bool:
        if perspective.requires_graph():
            return bool(self.graph and self.graph.is_available())
        return True

    async def _run_safe(
        self, perspective: BasePerspective, project_root: str
    ) -> PerspectiveResult:
        """Run a perspective, catching and wrapping any exception."""
        try:
            return await perspective.analyze(project_root)
        except Exception as e:
            log.error("Perspective '%s' failed: %s", perspective.name, e, exc_info=True)
            return PerspectiveResult(
                perspective_name=perspective.name,
                summary=f"Error: {e}",
                error=str(e),
            )


# ── Formatting helpers for IPC ─────────────────────────────────────────────

def format_results_as_text(results: list[PerspectiveResult]) -> str:
    """Render analysis results as a readable text block for the TUI message log."""
    lines: list[str] = []

    total_findings = sum(len(r.findings) for r in results)
    critical = sum(
        sum(1 for f in r.findings if f.severity == "critical") for r in results
    )
    high = sum(
        sum(1 for f in r.findings if f.severity == "high") for r in results
    )

    lines.append("## Analysis Complete\n")
    lines.append(
        f"**{total_findings} findings** across {len(results)} perspectives  "
        f"({critical} critical, {high} high)\n"
    )
    lines.append("---\n")

    for result in results:
        if result.error:
            lines.append(f"**{result.perspective_name}**: ERROR — {result.error}\n")
            continue

        icon = _severity_icon(result)
        lines.append(f"### {icon} {result.perspective_name.replace('_', ' ').title()}")
        lines.append(f"{result.summary}\n")

        # Show top 5 findings per perspective
        shown = result.findings[:5]
        for finding in shown:
            sev_tag = f"[{finding.severity.upper()}]"
            loc = f" `{finding.file_path}:{finding.start_line}`" if finding.file_path else ""
            lines.append(f"- {sev_tag} **{finding.title}**{loc}")
            if finding.suggestion:
                lines.append(f"  *{finding.suggestion}*")

        if len(result.findings) > 5:
            lines.append(f"  *(+{len(result.findings) - 5} more findings)*")
        lines.append("")

    lines.append("---")
    lines.append(
        "Run `/session` to save a full report or ask a follow-up question."
    )
    return "\n".join(lines)


def _severity_icon(result: PerspectiveResult) -> str:
    if any(f.severity == "critical" for f in result.findings):
        return "🔴"
    if any(f.severity == "high" for f in result.findings):
        return "🟠"
    if result.findings:
        return "🟡"
    return "✅"
