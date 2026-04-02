"""AgentManager — single owner of an active /agent run.

Orchestrates existing subsystems (task ledger, multi-agent, git, analysis)
through one coherent runtime with explicit phases and durable state.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from .state import AgentPhase, AgentPlan, AgentRun, load_run, save_run
from .toolbox import Toolbox

if TYPE_CHECKING:
    from ..agents.orchestrator import AgentOrchestrator
    from ..config import Config
    from ..tasks.ledger import TaskLedger

log = logging.getLogger("nala.agent_runtime.manager")


class AgentManager:
    """Central control plane for ``/agent`` runs."""

    def __init__(
        self,
        config: Config,
        project_root: Path,
        orchestrator: AgentOrchestrator | None = None,
        task_ledger: TaskLedger | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.toolbox = Toolbox(
            config, project_root,
            orchestrator=orchestrator,
            task_ledger=task_ledger,
        )
        self._run: AgentRun | None = load_run(project_root)
        if self._run and self._run.phase in (
            AgentPhase.DONE, AgentPhase.CANCELLED,
        ):
            self._run = None

    # ── Accessors ─────────────────────────────────────────────────────

    @property
    def current_run(self) -> AgentRun | None:
        return self._run

    @property
    def is_active(self) -> bool:
        return self._run is not None and self._run.phase not in (
            AgentPhase.IDLE, AgentPhase.DONE, AgentPhase.CANCELLED,
        )

    def set_orchestrator(self, orch: AgentOrchestrator) -> None:
        self.toolbox.set_orchestrator(orch)

    def set_task_ledger(self, ledger: TaskLedger) -> None:
        self.toolbox.set_task_ledger(ledger)

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self, objective: str, scope: str = "") -> AgentRun:
        """Create a new agent run with the given objective."""
        run = AgentRun(objective=objective, scope=scope)
        run.phase = AgentPhase.SCOPING

        task_id = self.toolbox.create_task(objective)
        run.current_task_id = task_id

        self._run = run
        save_run(self.project_root, run)
        log.info("Agent run started: %s — %s", run.run_id, objective)
        return run

    def _transition(self, phase: AgentPhase) -> None:
        if self._run is None:
            return
        self._run.phase = phase
        save_run(self.project_root, self._run)

    async def plan(self, topic: str = "") -> AsyncIterator[str]:
        """Generate a plan for the current (or new) objective."""
        if self._run is None:
            if topic:
                self.start(topic)
            else:
                yield "No active agent run. Use `/agent <objective>` first."
                return

        self._transition(AgentPhase.PLANNING)
        prompt = (
            f"Create a detailed step-by-step plan for: {self._run.objective}\n"
            f"Scope: {self._run.scope or 'entire project'}\n"
            "Format each step as a numbered list. Include risk assessment "
            "and verification commands at the end."
        )

        full_text: list[str] = []
        async for chunk in self.toolbox.stream_action_query(prompt):
            full_text.append(chunk)
            yield chunk

        self._run.plan = AgentPlan(
            steps=[f"(AI-generated plan — {len(full_text)} tokens)"],
            scope_description=self._run.scope or "entire project",
        )
        self._transition(AgentPhase.AWAITING_APPROVAL)

    async def run_execution(self) -> AsyncIterator[str]:
        """Execute the plan using the multi-agent team."""
        if self._run is None:
            yield "No active agent run."
            return

        self._transition(AgentPhase.EXECUTING)
        self._run.team_run_active = True
        save_run(self.project_root, self._run)

        try:
            summary = await self.toolbox.team_start(self._run.objective)
            yield summary
        except Exception as e:
            log.error("Agent execution failed: %s", e)
            yield f"Execution failed: {e}"
            self._run.phase = AgentPhase.BLOCKED
            save_run(self.project_root, self._run)
            return
        finally:
            if self._run:
                self._run.team_run_active = False

        self._transition(AgentPhase.REVIEWING)

    async def review(self) -> str:
        """Review current changes (git diff + status)."""
        if self._run:
            self._transition(AgentPhase.REVIEWING)
        diff = self.toolbox.git_diff()
        status = self.toolbox.git_status()
        return f"## Current Changes\n\n{diff}\n\n## Git Status\n\n{status}"

    async def verify(self) -> AsyncIterator[str]:
        """Run verification analysis."""
        if self._run:
            self._transition(AgentPhase.VERIFYING)

        prompt = (
            "Run a quick verification of the current codebase state. "
            "Check for: compilation errors, obvious bugs, test failures, "
            "and any regressions from recent changes."
        )
        async for chunk in self.toolbox.stream_query(prompt):
            yield chunk

        if self._run:
            self._transition(AgentPhase.DONE)
            self.toolbox.complete_task("Agent verification completed")
            save_run(self.project_root, self._run)

    async def hotspot(self) -> AsyncIterator[str]:
        """Run quick hotspot triage."""
        prompt = (
            "Analyze the codebase and identify the top 5 hotspots that "
            "would benefit most from improvement. Consider: complexity, "
            "code churn, error-prone patterns, and architectural risks. "
            "For each hotspot, suggest a specific actionable improvement."
        )
        async for chunk in self.toolbox.stream_query(prompt):
            yield chunk

    def status(self) -> str:
        """Return a formatted status summary."""
        parts: list[str] = []
        if self._run:
            parts.append(self._run.status_text())
        else:
            parts.append("No active agent run. Use `/agent <objective>` to start.")

        task_text = self.toolbox.task_status()
        if task_text and "(task ledger not available)" not in task_text:
            parts.append(f"\n## Tasks\n{task_text}")

        team_text = self.toolbox.team_status()
        if team_text and "No team run active" not in team_text:
            parts.append(f"\n## Team\n{team_text}")

        return "\n\n".join(parts)

    def stop(self) -> str:
        """Cancel the active run."""
        if self._run is None:
            return "No active agent run to cancel."
        self._run.phase = AgentPhase.CANCELLED
        save_run(self.project_root, self._run)
        old_id = self._run.run_id
        self._run = None
        return f"Agent run `{old_id}` cancelled."

    def resume(self) -> str:
        """Resume a paused or blocked run."""
        if self._run is None:
            saved = load_run(self.project_root)
            if saved and saved.phase not in (AgentPhase.DONE, AgentPhase.CANCELLED):
                self._run = saved
                return f"Resumed agent run `{saved.run_id}` (phase: {saved.phase.value})"
            return "No agent run to resume."
        return f"Agent run `{self._run.run_id}` is already active (phase: {self._run.phase.value})"

    async def handle_objective(self, objective: str) -> AsyncIterator[str]:
        """Start a new run and stream the action query response."""
        self.start(objective)
        self._transition(AgentPhase.EXECUTING)
        async for chunk in self.toolbox.stream_action_query(objective):
            yield chunk
        if self._run:
            self._transition(AgentPhase.REVIEWING)
