"""AgentManager — single owner of an active /agent run.

Orchestrates existing subsystems (task ledger, multi-agent, git, analysis)
through one coherent runtime with explicit phases and durable state.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from ..skills.registry import SkillRegistry
from .state import AgentPhase, AgentPlan, AgentRun, AutonomyLevel, load_run, save_run
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
        self._mode: str = "plan"
        self.skills = SkillRegistry(project_root)

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

    def set_mode(self, mode: str) -> None:
        allowed = {"observe", "plan", "patch", "autonomous"}
        if mode in allowed:
            self._mode = mode
            if self._run:
                self._run.autonomy = AutonomyLevel(mode)
                save_run(self.project_root, self._run)

    # ── Project brief + scoped guidance ────────────────────────────────

    def load_project_brief(self) -> str:
        """Read .nala/agent/project-brief.md if it exists."""
        brief = self.project_root / ".nala" / "agent" / "project-brief.md"
        if brief.exists():
            return brief.read_text(encoding="utf-8")
        return ""

    def load_scoped_guidance(self, scope_hint: str = "") -> str:
        """Load relevant scoped guidance files from .nala/agent/scopes/."""
        scopes_dir = self.project_root / ".nala" / "agent" / "scopes"
        if not scopes_dir.exists():
            return ""
        parts: list[str] = []
        for md_file in sorted(scopes_dir.glob("*.md")):
            if scope_hint and scope_hint.lower() not in md_file.stem.lower():
                continue
            content = md_file.read_text(encoding="utf-8")
            if content.strip():
                parts.append(content.strip())
        return "\n\n---\n\n".join(parts)

    # ── Verification recipes ──────────────────────────────────────────

    def detect_verification_commands(self) -> list[str]:
        """Detect project-appropriate verification commands."""
        root = self.project_root
        commands: list[str] = []
        if (root / "Cargo.toml").exists():
            commands.append("cargo check")
            if (root / "Cargo.lock").exists():
                commands.append("cargo test")
        if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
            commands.append("python -m ruff check .")
            if (root / "pytest.ini").exists() or (
                root / "pyproject.toml"
            ).exists():
                commands.append("python -m pytest --tb=short -q")
        if (root / "package.json").exists():
            pkg = root / "package.json"
            try:
                import json as _json
                data = _json.loads(pkg.read_text())
                scripts = data.get("scripts", {})
                if "test" in scripts:
                    commands.append("npm test")
                if "lint" in scripts:
                    commands.append("npm run lint")
            except Exception:
                commands.append("npm test")
        if (root / "Makefile").exists():
            commands.append("make check")
        return commands

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

        brief = self.load_project_brief()
        guidance = self.load_scoped_guidance(self._run.scope)
        verification_cmds = self.detect_verification_commands()

        context_parts = [
            f"Create a detailed step-by-step plan for: {self._run.objective}",
            f"Scope: {self._run.scope or 'entire project'}",
        ]
        if brief:
            context_parts.append(f"\n[PROJECT BRIEF]\n{brief}\n[END BRIEF]")
        if guidance:
            context_parts.append(
                f"\n[SCOPED GUIDANCE]\n{guidance}\n[END GUIDANCE]"
            )
        if verification_cmds:
            context_parts.append(
                f"\nAvailable verification: {', '.join(verification_cmds)}"
            )
        context_parts.append(
            "Format each step as a numbered list. Include risk assessment "
            "and verification commands at the end."
        )
        prompt = "\n".join(context_parts)

        full_text: list[str] = []
        async for chunk in self.toolbox.stream_action_query(prompt):
            full_text.append(chunk)
            yield chunk

        self._run.plan = AgentPlan(
            steps=[
                line.strip().lstrip("0123456789. ")
                for line in "".join(full_text).split("\n")
                if line.strip() and line.strip()[0].isdigit()
            ][:20] or [f"(AI-generated plan — {len(full_text)} chunks)"],
            scope_description=self._run.scope or "entire project",
            verification_commands=verification_cmds,
        )
        self._transition(AgentPhase.AWAITING_APPROVAL)

    async def approve(self, approved: bool = True) -> AsyncIterator[str]:
        """Handle plan approval or rejection."""
        if self._run is None:
            yield "No active agent run."
            return
        if self._run.phase != AgentPhase.AWAITING_APPROVAL:
            yield (
                f"Cannot approve in phase `{self._run.phase.value}`. "
                "Run `/agent plan` first."
            )
            return
        if approved:
            yield "Plan approved. Starting execution...\n"
            async for chunk in self.run_execution():
                yield chunk
        else:
            self._transition(AgentPhase.PLANNING)
            yield (
                "Plan rejected. Use `/agent plan <feedback>` to revise, "
                "or `/agent stop` to cancel."
            )

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
        branch = self.toolbox.git_branch()
        parts = ["## Current Changes\n"]
        if branch:
            parts.append(f"**Branch:** {branch}\n")
        parts.append(f"{diff}\n\n## Git Status\n\n{status}")
        return "\n".join(parts)

    async def verify(self) -> AsyncIterator[str]:
        """Run verification: execute detected commands then summarise."""
        if self._run:
            self._transition(AgentPhase.VERIFYING)

        commands = self.detect_verification_commands()
        cmd_results: list[str] = []

        if commands:
            yield "## Running verification commands\n\n"
            for cmd in commands:
                yield f"**`{cmd}`** → "
                result = self.toolbox.run_shell(cmd)
                passed = result["exit_code"] == 0
                status = "PASS" if passed else "FAIL"
                yield f"{status}\n"
                cmd_results.append(
                    f"- `{cmd}` → {status}"
                    + (f"\n  ```\n{result['output'][-500:]}\n  ```" if not passed else "")
                )
            yield "\n"
        else:
            yield "No project-specific verification commands detected.\n"

        yield "## AI Verification Summary\n\n"
        prompt = (
            "Review the current codebase state and the following verification results:\n"
            + "\n".join(cmd_results)
            + "\nCheck for: compilation errors, obvious bugs, test failures, "
            "and any regressions from recent changes. Summarize findings."
        )
        async for chunk in self.toolbox.stream_query(prompt):
            yield chunk

        if self._run:
            from .state import AgentVerification
            self._run.verification = AgentVerification(
                commands_executed=[c for c in commands],
                results=cmd_results,
                passed=all("PASS" in r for r in cmd_results) if cmd_results else None,
            )
            self._transition(AgentPhase.DONE)
            self.toolbox.complete_task("Agent verification completed")
            save_run(self.project_root, self._run)

    async def hotspot(self) -> AsyncIterator[str]:
        """Run quick hotspot triage using the built-in skill."""
        prompt = self.skills.resolve("triage-hotspots")
        if prompt is None:
            prompt = (
                "Analyze the codebase and identify the top 5 hotspots."
            )
        async for chunk in self.toolbox.stream_query(prompt):
            yield chunk

    def status(self) -> str:
        """Return a formatted status summary."""
        parts: list[str] = []
        if self._run:
            parts.append(self._run.status_text())
            parts.append(f"**Autonomy:** {self._mode.upper()}")
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

        brief = self.load_project_brief()
        guidance = self.load_scoped_guidance()
        enriched = objective
        if brief:
            enriched = (
                f"[PROJECT BRIEF]\n{brief[:2000]}\n[END BRIEF]\n\n"
                + enriched
            )
        if guidance:
            enriched = (
                f"[SCOPED GUIDANCE]\n{guidance[:1000]}\n[END GUIDANCE]\n\n"
                + enriched
            )

        async for chunk in self.toolbox.stream_action_query(enriched):
            yield chunk
        if self._run:
            self._transition(AgentPhase.REVIEWING)
