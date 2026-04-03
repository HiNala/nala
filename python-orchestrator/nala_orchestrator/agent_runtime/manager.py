"""AgentManager — single owner of an active /agent run.

Orchestrates existing subsystems (task ledger, multi-agent, git, analysis)
through one coherent runtime with explicit phases and durable state.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from ..models.registry import ModelRegistry
from ..models.router import ModelRouter
from ..models.types import TaskType
from ..research.service import ResearchService
from ..skills.registry import SkillRegistry
from .executor import MissionExecutor
from .mission_writer import MissionWriter
from .state import (
    AgentPhase,
    AgentPlan,
    AgentRun,
    AutonomyLevel,
    MissionFile,
    MissionStatus,
    load_run,
    save_run,
)
from .toolbox import Toolbox
from .workers import WorkerRegistry, WorkerRole, WorkerStatus

if TYPE_CHECKING:
    from ..agents.orchestrator import AgentOrchestrator
    from ..config import Config
    from ..graph.context import GraphContextProvider
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
        self.research = ResearchService(config, project_root, orchestrator)

        # Multi-model routing
        self.model_registry = ModelRegistry(config)
        task_overrides = {
            TaskType(k): v for k, v in config.model_overrides.items()
            if k in {t.value for t in TaskType}
        }
        self.model_router = ModelRouter(
            self.model_registry,
            overrides=task_overrides or None,
            primary_provider=config.llm_provider,
            primary_model=config.active_model(),
        )

        self._graph_ctx: GraphContextProvider | None = None
        self._checkpoints: list[dict] = []
        self._pending_choices: list[str] = []
        self._pending_missions: list[MissionFile] | None = None
        self._pending_writer: MissionWriter | None = None
        self._original_branch: str = "main"
        run_id = self._run.run_id if self._run else ""
        self._workers = WorkerRegistry(run_id)
        if self._run and self._run.workers:
            self._workers = WorkerRegistry.from_list(
                self._run.workers, run_id,
            )

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
        self.research.set_orchestrator(orch)

    def set_graph_context(self, graph_ctx: GraphContextProvider) -> None:
        """Attach a graph context provider for mission planning."""
        self._graph_ctx = graph_ctx

    async def ensure_registry(self) -> None:
        """Load or build the model registry (called on first /models or agent launch)."""
        await self.model_registry.ensure_loaded()

    async def refresh_registry(self) -> None:
        """Force-rebuild the model registry by probing all providers."""
        await self.model_registry.refresh()

    def models_report(self) -> str:
        """Human-readable report of available models + routing table."""
        parts = [self.model_registry.format_status_report()]
        parts.append("")
        parts.append(self.model_router.format_routing_table())
        return "\n".join(parts)

    def route_task(self, task_type: TaskType) -> tuple[str, str]:
        """Return (provider, model_id) for a task type."""
        result = self.model_router.route(task_type)
        return result.provider.value, result.model_id

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
        research_ctx = self.research_context()
        if research_ctx:
            context_parts.append(f"\n{research_ctx}")
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
        """Review current changes (git diff + status + quick analysis)."""
        if self._run:
            self._transition(AgentPhase.REVIEWING)
        diff = self.toolbox.git_diff()
        status = self.toolbox.git_status()
        branch = self.toolbox.git_branch()
        parts = ["## Current Changes\n"]
        if branch:
            parts.append(f"**Branch:** {branch}\n")
        parts.append(f"{diff}\n\n## Git Status\n\n{status}")

        # Quick code analysis alongside the review
        try:
            from ..perspectives.engine import PerspectivesEngine, format_results_as_text
            graph_conn = None
            try:
                from ..graph.connection import GraphConnection
                graph_conn = GraphConnection(self.config)
                if not graph_conn.connect():
                    graph_conn = None
            except Exception:
                pass
            engine = PerspectivesEngine(self.config, graph=graph_conn)
            results = await engine.run_quick(str(self.project_root))
            if results:
                findings_count = sum(len(r.findings) for r in results)
                if findings_count > 0:
                    parts.append(f"\n## Code Analysis ({findings_count} findings)\n")
                    parts.append(format_results_as_text(results))
            if graph_conn:
                graph_conn.close()
        except Exception as exc:
            log.debug("Review analysis skipped: %s", exc)

        return "\n".join(parts)

    async def verify(self) -> AsyncIterator[str]:
        """Run verification: test commands + code analysis perspectives."""
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

        # Run quick static analysis (complexity, security, dependencies)
        analysis_text = ""
        try:
            yield "## Code Analysis\n\n"
            from ..perspectives.engine import PerspectivesEngine, format_results_as_text
            graph_conn = None
            try:
                from ..graph.connection import GraphConnection
                graph_conn = GraphConnection(self.config)
                if not graph_conn.connect():
                    graph_conn = None
            except Exception:
                pass
            engine = PerspectivesEngine(self.config, graph=graph_conn)
            results = await engine.run_quick(str(self.project_root))
            if results:
                analysis_text = format_results_as_text(results)
                yield analysis_text + "\n\n"
            else:
                yield "No analysis findings from quick scan.\n\n"
            if graph_conn:
                graph_conn.close()
        except Exception as exc:
            log.debug("Verification analysis skipped: %s", exc)
            yield f"Analysis skipped: {exc}\n\n"

        yield "## AI Verification Summary\n\n"
        prompt = (
            "Review the current codebase state and the following verification results:\n"
            + "\n".join(cmd_results)
        )
        if analysis_text:
            prompt += f"\n\nStatic analysis findings:\n{analysis_text[:3000]}"
        prompt += (
            "\nCheck for: compilation errors, obvious bugs, test failures, "
            "security issues, and any regressions from recent changes. Summarize findings."
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

        worker_text = self._workers.format_summary()
        if "No workers" not in worker_text:
            parts.append(f"\n## Workers\n{worker_text}")

        choices = self.suggest_next_steps()
        if choices:
            parts.append("\n## Next Steps")
            for c in choices:
                parts.append(f"  - {c}")

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

    # ── Orchestration: mission-driven execution (P7-02) ─────────────

    async def start_objective(
        self, objective: str, autonomy: str = "autonomous"
    ) -> AsyncIterator[str]:
        """Full orchestration loop: research → plan → approve → execute.

        Yields streaming progress text for the TUI.
        """
        run = self.start(objective)
        try:
            run.autonomy = AutonomyLevel(autonomy)
        except ValueError:
            run.autonomy = AutonomyLevel.AUTONOMOUS
        save_run(self.project_root, run)

        from .. import git_ops

        original_branch = git_ops.current_branch(self.project_root) or "main"
        if git_ops.is_git_repo(self.project_root):
            branch = git_ops.create_agent_branch(self.project_root, run.run_id)
            if branch:
                run.git_branch = branch
                save_run(self.project_root, run)
                yield f"**Git:** Created branch `{branch}`\n\n"
            else:
                yield "**Git:** Could not create agent branch (continuing on current branch)\n\n"

        # Phase 1: Research
        self._transition(AgentPhase.RESEARCHING)
        yield "## Phase 1: Research\n\n"
        research_context = ""
        try:
            research_chunks: list[str] = []
            async for chunk in self.research.research(
                f"Research context and requirements for: {objective}"
            ):
                research_chunks.append(chunk)
            research_context = "".join(research_chunks)
            if research_context.strip():
                yield f"Research gathered ({len(research_context)} chars)\n\n"
            else:
                yield "No external research available — proceeding with local context.\n\n"
        except Exception as exc:
            yield f"Research phase skipped ({type(exc).__name__}: {str(exc)[:60]}). Proceeding with local context.\n\n"

        # Phase 2: Generate missions
        self._transition(AgentPhase.GENERATING_MISSIONS)
        yield "## Phase 2: Generating Mission Plan\n\n"

        plan_prompt = self._build_plan_prompt(objective, research_context)
        plan_chunks: list[str] = []
        try:
            async for chunk in self.toolbox.stream_action_query(plan_prompt):
                plan_chunks.append(chunk)
        except Exception as exc:
            yield f"**Plan generation failed:** {type(exc).__name__}: {exc}\n"
            yield "  Check your API key with `/settings` or `/models`. Use `/agent objective` to retry.\n"
            self._transition(AgentPhase.BLOCKED)
            return

        raw_plan = "".join(plan_chunks)
        missions = MissionWriter.parse_plan_output(raw_plan)

        if not missions:
            missions = self._fallback_missions(objective)

        writer = MissionWriter(self.project_root, run.run_id)
        paths = writer.write_missions(missions)
        run.missions = [
            {"id": m.id, "title": m.title, "status": m.status.value}
            for m in missions
        ]
        run.missions_total = len(missions)
        save_run(self.project_root, run)

        plan_summary = self._format_mission_plan(missions)
        yield plan_summary + "\n"

        if git_ops.is_git_repo(self.project_root):
            git_ops.commit_milestone(
                self.project_root,
                f"[nala] Plan: {len(missions)} missions for '{objective[:50]}'",
            )

        # Phase 3: Await approval
        if run.autonomy != AutonomyLevel.AUTONOMOUS:
            self._transition(AgentPhase.AWAITING_APPROVAL)
            yield (
                "\n**Plan ready.** Use `/agent approve` to start execution "
                "or `/agent reject` to revise.\n"
            )
            self._pending_missions = missions
            self._pending_writer = writer
            self._original_branch = original_branch
            return

        # Phase 4: Execute missions
        yield "\n## Phase 3: Executing Missions\n\n"
        async for chunk in self._execute_missions(run, missions, writer):
            yield chunk

        # Phase 5: Final summary
        if git_ops.is_git_repo(self.project_root):
            diff = git_ops.get_run_diff_summary(self.project_root, original_branch)
            yield f"\n## Git Summary\n\n{diff}\n"

        self._transition(AgentPhase.DONE)
        yield f"\n**Agent run `{run.run_id}` complete.**\n"

    async def approve_missions(self, approved: bool = True) -> AsyncIterator[str]:
        """Handle mission plan approval after start_objective paused for approval."""
        if self._run is None:
            yield "No active agent run."
            return

        missions = getattr(self, "_pending_missions", None)
        writer = getattr(self, "_pending_writer", None)
        original_branch = getattr(self, "_original_branch", "main")

        if not missions or not writer:
            async for chunk in self.approve(approved):
                yield chunk
            return

        if not approved:
            self._transition(AgentPhase.PLANNING)
            self._pending_missions = None
            self._pending_writer = None
            yield "Mission plan rejected. Use `/agent <objective>` to restart with a new plan.\n"
            return

        yield "## Executing Missions\n\n"
        async for chunk in self._execute_missions(self._run, missions, writer):
            yield chunk

        from .. import git_ops
        if git_ops.is_git_repo(self.project_root):
            diff = git_ops.get_run_diff_summary(self.project_root, original_branch)
            yield f"\n## Git Summary\n\n{diff}\n"

        self._transition(AgentPhase.DONE)
        yield f"\n**Agent run `{self._run.run_id}` complete.**\n"
        self._pending_missions = None
        self._pending_writer = None

    async def _execute_missions(
        self,
        run: AgentRun,
        missions: list[MissionFile],
        writer: MissionWriter,
    ) -> AsyncIterator[str]:
        """Inner mission execution loop with git milestones."""
        from .. import git_ops

        self._transition(AgentPhase.EXECUTING_MISSIONS)
        executor = MissionExecutor(self.config, self.project_root, run.run_id)

        async for chunk in executor.execute_all(missions):
            yield chunk

        completed = sum(
            1 for r in executor.results.values() if r.success
        )
        run.missions_completed = completed
        run.missions = [
            {"id": m.id, "title": m.title, "status": m.status.value}
            for m in writer.load_missions()
        ]
        save_run(self.project_root, run)

        if git_ops.is_git_repo(self.project_root) and completed > 0:
            git_ops.commit_milestone(
                self.project_root,
                f"[nala] Executed {completed}/{len(missions)} missions for run {run.run_id}",
            )

    def _build_plan_prompt(self, objective: str, research_context: str) -> str:
        brief = self.load_project_brief()
        guidance = self.load_scoped_guidance()

        parts = [
            "You are a senior software architect planning an implementation.",
            f"The user wants: {objective}",
        ]
        if brief:
            parts.append(f"\n[PROJECT BRIEF]\n{brief[:2000]}\n[END BRIEF]")
        if guidance:
            parts.append(f"\n[SCOPED GUIDANCE]\n{guidance[:1000]}\n[END GUIDANCE]")
        if research_context:
            parts.append(f"\n[RESEARCH CONTEXT]\n{research_context[:3000]}\n[END RESEARCH]")

        if self._graph_ctx:
            try:
                graph_block = self._graph_ctx.context_for_planning(objective, max_chars=4000)
                if graph_block:
                    parts.append(f"\n{graph_block}")
            except Exception as exc:
                log.debug("Graph context for planning failed: %s", exc)

        parts.append("""
Generate a JSON array of missions. Each mission object must have:
- "id": unique string like "mission-1"
- "title": short descriptive title
- "objective": 1-2 sentence description
- "task_type": one of "plan", "code", "design", "research", "review", "verify"
- "dependencies": array of mission IDs that must complete first (or empty)
- "parallel_group": group ID for parallel execution, or "sequential"
- "scope": array of file/directory paths this mission touches
- "steps": array of concrete implementation steps
- "verification": how to confirm the mission is done
- "acceptance_criteria": array of verifiable outcomes

Rules:
- Order missions by dependency (foundation first, integration last)
- Group independent missions into parallel groups where safe
- Keep each mission focused (1 concern per mission)
- Include a verification/review mission at the end
- Return ONLY the JSON array, no other text
""")
        return "\n".join(parts)

    def _fallback_missions(self, objective: str) -> list[MissionFile]:
        """Create a minimal 3-mission plan when LLM output can't be parsed."""
        return [
            MissionFile(
                id="mission-1",
                title="Research and scope",
                objective=f"Analyze the codebase and determine scope for: {objective}",
                task_type="research",
                steps=["Examine existing code structure", "Identify files to change", "Document approach"],
                acceptance_criteria=["Scope documented"],
            ),
            MissionFile(
                id="mission-2",
                title="Implement changes",
                objective=f"Implement: {objective}",
                task_type="code",
                dependencies=["mission-1"],
                steps=["Make the required code changes", "Add error handling", "Test locally"],
                acceptance_criteria=["Changes compile", "Core functionality works"],
            ),
            MissionFile(
                id="mission-3",
                title="Verify and review",
                objective="Verify all changes work correctly",
                task_type="review",
                dependencies=["mission-2"],
                steps=["Run tests", "Review diff", "Check for regressions"],
                acceptance_criteria=["All tests pass", "No regressions"],
            ),
        ]

    def _format_mission_plan(self, missions: list[MissionFile]) -> str:
        lines = [f"### Mission Plan ({len(missions)} missions)\n"]
        for i, m in enumerate(missions, 1):
            deps = f" (depends on: {', '.join(m.dependencies)})" if m.dependencies else ""
            group = f" [parallel: {m.parallel_group}]" if m.parallel_group != "sequential" else ""
            lines.append(f"{i}. **{m.title}** — {m.task_type}{deps}{group}")
            lines.append(f"   {m.objective[:120]}")
        return "\n".join(lines)

    # ── Worker management (M32/M33) ───────────────────────────────────

    def spawn_worker(
        self,
        objective: str,
        role: str = "implement",
        scope: str = "",
        use_worktree: bool = False,
    ) -> str:
        """Spawn a worker for the current run. Returns status message."""
        if self._run is None:
            return "No active agent run."
        if not self._workers.can_spawn():
            return "Worker limit reached (max 3). Cancel one first."

        wt_path = ""
        if use_worktree:
            from .. import git_ops
            label = f"worker-{self._workers.count + 1}"
            path = git_ops.create_worktree(self.project_root, label)
            if path:
                wt_path = path

        try:
            worker_role = WorkerRole(role)
        except ValueError:
            worker_role = WorkerRole.IMPLEMENT

        worker = self._workers.spawn(
            objective=objective,
            role=worker_role,
            scope=scope,
            worktree_path=wt_path,
        )
        if worker is None:
            return "Failed to spawn worker."
        self._run.workers = self._workers.to_list()
        save_run(self.project_root, self._run)
        return f"Spawned worker `{worker.worker_id}` ({worker.role.value}): {objective[:60]}"

    def list_workers(self) -> str:
        return self._workers.format_summary()

    def cancel_worker(self, worker_id: str) -> str:
        if self._workers.cancel(worker_id):
            if self._run:
                self._run.workers = self._workers.to_list()
                save_run(self.project_root, self._run)
            return f"Worker `{worker_id}` cancelled."
        return f"Worker `{worker_id}` not found or already finished."

    def send_to_worker(self, worker_id: str, message: str) -> str:
        """Send a message to a worker (via message bus)."""
        worker = self._workers.get(worker_id)
        if worker is None:
            return f"Worker `{worker_id}` not found."
        if worker.status not in (WorkerStatus.PENDING, WorkerStatus.RUNNING):
            return f"Worker `{worker_id}` is {worker.status.value}, cannot message."
        self.toolbox.send_worker_message(worker_id, message)
        return f"Message sent to `{worker_id}`."

    def get_worker_detail(self, worker_id: str) -> str:
        """Get detailed info for a worker (for attach view)."""
        worker = self._workers.get(worker_id)
        if worker is None:
            return f"Worker `{worker_id}` not found."
        lines = [
            f"**Worker** `{worker.worker_id}`",
            f"**Role:** {worker.role.value}",
            f"**Status:** {worker.status.value}",
            f"**Objective:** {worker.objective}",
        ]
        if worker.scope:
            lines.append(f"**Scope:** {worker.scope}")
        if worker.worktree_path:
            lines.append(f"**Worktree:** {worker.worktree_path}")
        if worker.result_summary:
            lines.append(f"\n**Result:**\n{worker.result_summary}")
        if worker.files_touched:
            lines.append(f"**Files:** {', '.join(worker.files_touched)}")
        return "\n".join(lines)

    # ── Git review / SCM (M34) ────────────────────────────────────────

    def scm_overview(self) -> str:
        """Full SCM overview including worktrees."""
        from .. import git_review
        return git_review.scm_overview(self.project_root)

    def branch_review(self, base: str = "main", head: str = "HEAD") -> str:
        from .. import git_review
        return git_review.branch_review(self.project_root, base, head)

    def blame_file(self, file_path: str, start: int = 1, end: int = 0) -> str:
        from .. import git_ops
        return git_ops.blame_summary(self.project_root, file_path, start, end)

    def worktree_list(self) -> str:
        from .. import git_ops
        return git_ops.worktree_status(self.project_root)

    def worktree_create(self, label: str) -> str:
        from .. import git_ops
        path = git_ops.create_worktree(self.project_root, label)
        if path:
            return f"Created worktree `{label}` at `{path}`"
        return f"Failed to create worktree `{label}`."

    def worktree_cleanup(self, label: str) -> str:
        from .. import git_ops
        if git_ops.cleanup_worktree(self.project_root, label):
            return f"Removed worktree `{label}`."
        return f"Failed to remove worktree `{label}`."

    # ── Research (M35) ────────────────────────────────────────────────

    async def do_research(self, question: str) -> AsyncIterator[str]:
        """Run explicit web research. Yields streaming output."""
        if self._run:
            self._transition(AgentPhase.RESEARCHING)
        async for chunk in self.research.research(question):
            yield chunk
        if self._run and self._run.phase == AgentPhase.RESEARCHING:
            self._transition(AgentPhase.REVIEWING)

    def research_context(self) -> str:
        """Inject recent research into LLM context."""
        return self.research.format_research_context()

    # ── Pause / checkpoint (M36) ──────────────────────────────────────

    def pause(self) -> str:
        """Pause the active run."""
        if self._run is None:
            return "No active agent run to pause."
        if self._run.phase in (
            AgentPhase.DONE, AgentPhase.CANCELLED, AgentPhase.PAUSED,
        ):
            return f"Agent run is already {self._run.phase.value}."
        prev = self._run.phase.value
        self._transition(AgentPhase.PAUSED)
        return f"Agent run paused (was {prev}). Use `/agent resume` to continue."

    def checkpoint(self, label: str = "") -> str:
        """Save a checkpoint of the current run state."""
        if self._run is None:
            return "No active agent run."
        from datetime import UTC, datetime
        cp = {
            "label": label or f"cp-{len(self._checkpoints) + 1}",
            "phase": self._run.phase.value,
            "objective": self._run.objective,
            "plan_steps": self._run.plan.steps if self._run.plan else [],
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._checkpoints.append(cp)
        self._run.checkpoints = self._checkpoints
        save_run(self.project_root, self._run)
        return f"Checkpoint **{cp['label']}** saved (phase: {cp['phase']})."

    def list_checkpoints(self) -> str:
        if not self._checkpoints:
            return "No checkpoints saved."
        lines = ["**Checkpoints:**"]
        for i, cp in enumerate(self._checkpoints):
            lines.append(
                f"  {i + 1}. `{cp['label']}` — {cp['phase']} ({cp['created_at'][:19]})"
            )
        return "\n".join(lines)

    def restore_checkpoint(self, index: int) -> str:
        """Restore run state to a checkpoint."""
        if not self._checkpoints:
            return "No checkpoints to restore."
        if index < 0 or index >= len(self._checkpoints):
            return f"Invalid checkpoint index. Valid: 0 to {len(self._checkpoints) - 1}."
        cp = self._checkpoints[index]
        if self._run is None:
            return "No active agent run."
        try:
            self._run.phase = AgentPhase(cp["phase"])
        except ValueError:
            self._run.phase = AgentPhase.IDLE
        save_run(self.project_root, self._run)
        return f"Restored to checkpoint **{cp['label']}** (phase: {cp['phase']})."

    # ── Human-in-the-loop choices (M36) ───────────────────────────────

    def suggest_next_steps(self) -> list[str]:
        """Return context-appropriate next-step suggestions."""
        if self._run is None:
            return ["Type `/agent <objective>` to start a new run."]

        phase = self._run.phase
        choices: list[str] = []
        if phase == AgentPhase.PLANNING:
            choices = [
                "`/agent approve` — approve plan and begin execution",
                "`/agent reject` — revise the plan",
                "`/agent mode <level>` — change autonomy level",
                "`/agent pause` — save progress and pause",
            ]
        elif phase == AgentPhase.AWAITING_APPROVAL:
            choices = [
                "`/agent approve` — approve and proceed",
                "`/agent reject` — reject and re-plan",
                "`/agent review` — review the diff first",
            ]
        elif phase in (AgentPhase.EXECUTING, AgentPhase.EXECUTING_MISSIONS):
            choices = [
                "`/agent status` — check progress",
                "`/agent workers` — inspect workers",
                "`/agent pause` — pause execution",
                "`/agent stop` — cancel the run",
            ]
        elif phase == AgentPhase.VERIFYING:
            choices = [
                "`/agent status` — check verification progress",
                "`/agent review` — review changes",
            ]
        elif phase == AgentPhase.REVIEWING:
            choices = [
                "`/agent verify` — run verification",
                "`/agent checkpoint` — save a checkpoint",
                "`/agent stop` — mark as done",
                "`/agent research <q>` — look up something",
            ]
        elif phase == AgentPhase.PAUSED:
            choices = [
                "`/agent resume` — continue where you left off",
                "`/agent status` — check current state",
                "`/agent stop` — cancel the run",
            ]
        elif phase == AgentPhase.BLOCKED:
            choices = [
                "`/agent resume` — retry after fixing the issue",
                "`/agent workers` — check worker status",
                "`/agent stop` — cancel the run",
            ]
        elif phase == AgentPhase.DONE:
            choices = [
                "`/agent review` — final review",
                "`/agent scm` — check git state",
                "Start a new `/agent <objective>`",
            ]
        else:
            choices = ["`/agent status` — check current state"]
        return choices

    @property
    def pending_choices(self) -> list[str]:
        return self.suggest_next_steps()

    def notification_priority(self) -> str:
        """Determine whether to interrupt or quietly update.

        Returns 'interrupt' for decisions requiring user input,
        'quiet' for progress milestones.
        """
        if self._run is None:
            return "quiet"
        phase = self._run.phase
        if phase in (AgentPhase.AWAITING_APPROVAL, AgentPhase.BLOCKED):
            return "interrupt"
        if phase in (AgentPhase.EXECUTING, AgentPhase.VERIFYING, AgentPhase.RESEARCHING):
            return "quiet"
        return "quiet"
