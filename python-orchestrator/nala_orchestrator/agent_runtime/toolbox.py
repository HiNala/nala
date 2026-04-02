"""Toolbox — wraps existing Nala subsystems for the agent runtime.

Instead of reimplementing, the toolbox provides a single interface that
the ``AgentManager`` uses to call into indexing, git, analysis,
task ledger, multi-agent, and action execution.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.orchestrator import AgentOrchestrator
    from ..config import Config
    from ..multi_agent.lead import LeadAgent
    from ..tasks.ledger import TaskLedger

log = logging.getLogger("nala.agent_runtime.toolbox")


class Toolbox:
    """Façade over Nala's subsystems."""

    def __init__(
        self,
        config: Config,
        project_root: Path,
        orchestrator: AgentOrchestrator | None = None,
        task_ledger: TaskLedger | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self._orchestrator = orchestrator
        self._task_ledger = task_ledger
        self._lead_agent: LeadAgent | None = None

    @property
    def orchestrator(self) -> AgentOrchestrator | None:
        return self._orchestrator

    def set_orchestrator(self, orch: AgentOrchestrator) -> None:
        self._orchestrator = orch

    @property
    def task_ledger(self) -> TaskLedger | None:
        return self._task_ledger

    def set_task_ledger(self, ledger: TaskLedger) -> None:
        self._task_ledger = ledger

    # ── Git ────────────────────────────────────────────────────────────

    def git_diff(self) -> str:
        from ..git_ops import diff_summary
        return diff_summary(self.project_root)

    def git_status(self) -> str:
        from ..git_ops import full_status
        return full_status(self.project_root)

    def git_branch(self) -> str:
        from ..git_ops import branch_info
        return branch_info(self.project_root)

    # ── Task ledger ───────────────────────────────────────────────────

    def create_task(self, objective: str) -> str:
        if self._task_ledger is None:
            return "(task ledger not available)"
        task = self._task_ledger.create_task(objective)
        return task.id

    def task_status(self) -> str:
        if self._task_ledger is None:
            return "(task ledger not available)"
        return self._task_ledger.status_text()

    def complete_task(self, summary: str = "") -> str:
        if self._task_ledger is None:
            return "(task ledger not available)"
        task = self._task_ledger.complete_current(summary)
        return f"Task {task.id} completed" if task else "No active task"

    # ── Multi-agent ───────────────────────────────────────────────────

    def _ensure_lead(self) -> LeadAgent:
        if self._lead_agent is None:
            from ..multi_agent.lead import LeadAgent
            self._lead_agent = LeadAgent(self.config, str(self.project_root))
        return self._lead_agent

    async def team_start(self, objective: str) -> str:
        lead = self._ensure_lead()
        result = await lead.run(objective)
        return result.final_summary or "Team run completed."

    def team_status(self) -> str:
        if self._lead_agent is None:
            return "No team run active."
        return self._lead_agent.get_status()

    async def team_cancel(self) -> str:
        if self._lead_agent is not None:
            self._lead_agent = None
        return "Team run cancelled."

    # ── Analysis ──────────────────────────────────────────────────────

    async def run_analysis(self, perspective: str = "quick") -> str:
        if self._orchestrator is None:
            return "(orchestrator not available)"
        from ..perspectives.engine import PerspectivesEngine, format_results_as_text
        engine = PerspectivesEngine(self.config)
        results = await engine.run(
            str(self.project_root),
            perspective if perspective != "all" else None,
        )
        return format_results_as_text(results)

    # ── LLM queries ──────────────────────────────────────────────────

    async def stream_query(self, message: str):
        if self._orchestrator is None:
            yield "(orchestrator not available)"
            return
        async for chunk in self._orchestrator.stream_query(message):
            yield chunk

    async def stream_action_query(self, message: str):
        if self._orchestrator is None:
            yield "(orchestrator not available)"
            return
        async for chunk in self._orchestrator.stream_query_with_actions(message):
            yield chunk
