"""Mission 32: Main agent brain — the central decision-maker.

Receives every user input, classifies it, and either:
  - Answers directly (simple questions, single-file tasks)
  - Decomposes into a wave plan and spawns sub-agents (complex tasks)

Wires together: TaskClassifier → TaskPlanner → wave execution → ResultSynthesizer
→ ShellMessageBus → TUI
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nala_orchestrator.agents.registry import AgentRegistry
    from nala_orchestrator.agents.terminal import TerminalDetector
    from nala_orchestrator.shell.message_bus import ShellMessageBus

from .classifier import ClassifiedTask, TaskClassifier
from .planner import AgentTask, ExecutionPlan, TaskPlanner, Wave
from .synthesizer import AgentResult, ResultSynthesizer, WaveSummary

log = logging.getLogger(__name__)

_MAX_WAVE_RETRIES = 1  # One retry per failed task


@dataclass
class BrainConfig:
    project_root: Path
    nala_dir: Path
    max_parallel_agents: int = 3
    agent_timeout: int = 180


class AgentBrain:
    """Central orchestrator — routes user input through the classify → plan → execute loop."""

    def __init__(
        self,
        config: BrainConfig,
        bus: ShellMessageBus,
        registry: AgentRegistry | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.registry = registry
        self._classifier = TaskClassifier()
        self._planner = TaskPlanner()
        self._synthesizer = ResultSynthesizer()
        self._running_plan: ExecutionPlan | None = None

    # ── Public entry point ─────────────────────────────────────────────────

    async def handle(self, user_input: str) -> bool:
        """Handle one user message.

        Returns True if the brain handled it (spawned sub-agents or will
        handle directly), False if the caller should fall through to the
        regular LLM chat path.
        """
        task = self._classifier.classify(user_input, self.config.project_root)
        log.debug("Classified %r → complexity=%s intent=%s", user_input[:60],
                  task.complexity, task.intent)

        # Direct path: simple or single-file → let the LLM handle it
        if task.is_direct:
            return False

        # Multi-agent path
        plan = self._planner.plan(task, self.config.project_root)
        self._running_plan = plan

        if plan.requires_user_approval:
            await self._present_plan(plan)
            approved = await self._await_approval()
            if not approved:
                self.bus.post_text("nala", "Plan cancelled.")
                self._running_plan = None
                return True
        else:
            self.bus.post_text("nala", f"Starting plan: {plan.summary()}")

        asyncio.create_task(self._execute_plan(plan))
        return True

    def stop(self) -> None:
        """Cancel all running agents."""
        if self.registry:
            for handle in self.registry.get_active():
                try:
                    from nala_orchestrator.agents.terminal import TerminalDetector
                    strategy = TerminalDetector.get_strategy_for_handle(
                        self.config.project_root, handle
                    )
                    strategy.kill_agent(handle)
                except Exception:
                    pass
        self._running_plan = None

    # ── Private ────────────────────────────────────────────────────────────

    async def _present_plan(self, plan: ExecutionPlan) -> None:
        self.bus.post_text("nala", plan.summary())
        self.bus.post_approval(
            source="nala",
            content="Execute this plan? [y] Yes  [n] Cancel  [e] Edit",
            options=["y", "n", "e"],
            metadata={"plan_id": id(plan)},
        )

    async def _await_approval(self, timeout: float = 120) -> bool:
        # Find the most recent pending approval from nala
        pending = self.bus.get_pending_approvals()
        if not pending:
            return True
        msg = pending[-1]
        response = await self.bus.wait_for_response(msg.message_id, timeout=timeout)
        return response is not None and response.lower() in {"y", "yes"}

    async def _execute_plan(self, plan: ExecutionPlan) -> None:
        all_results: list[AgentResult] = []
        wave_summaries: list[WaveSummary] = []
        context = ""

        for wave in plan.waves:
            self.bus.post_status("nala", f"Wave {wave.wave_number}: {wave.description}")
            try:
                results = await self._execute_wave(wave, context)
            except Exception as e:
                log.error("Wave %d failed: %s", wave.wave_number, e)
                self.bus.post_error("nala", f"Wave {wave.wave_number} error: {e}")
                continue

            summary = self._synthesizer.synthesize(
                wave.wave_number, wave.description, results
            )
            wave_summaries.append(summary)
            all_results.extend(results)

            # Persist and load context for next wave
            self._synthesizer.save_wave_results(
                self.config.nala_dir, wave.wave_number, results
            )
            context = self._synthesizer.load_wave_context(
                self.config.nala_dir, wave.wave_number
            )
            # Post wave summary
            self.bus.post_text("nala", f"Wave {wave.wave_number} complete:\n{summary.highlights}")

        synthesis = self._synthesizer.merge_waves(plan.objective, wave_summaries, all_results)
        self.bus.post_text("nala", synthesis.format_for_display())
        self._running_plan = None

    async def _execute_wave(self, wave: Wave, context: str) -> list[AgentResult]:
        if wave.parallel:
            coros = [self._run_task(t, context) for t in wave.tasks]
            return list(await asyncio.gather(*coros, return_exceptions=False))
        else:
            results: list[AgentResult] = []
            for task in wave.tasks:
                results.append(await self._run_task(task, context))
            return results

    async def _run_task(self, task: AgentTask, context: str) -> AgentResult:
        """Run one agent task, with one retry on failure."""
        self.bus.post_status(task.task_id, f"Started: {task.mission[:60]}")
        try:
            result = await asyncio.wait_for(
                self._spawn_and_wait(task, context),
                timeout=task.timeout_seconds,
            )
            self.bus.post_status(task.task_id, f"Done: {result.summary[:80]}")
            return result
        except asyncio.TimeoutError:
            self.bus.post_error(task.task_id, "Timed out — retrying with reduced scope")
            return await self._retry_task(task, context)
        except Exception as e:
            self.bus.post_error(task.task_id, f"Failed: {e}")
            return await self._retry_task(task, context)

    async def _retry_task(self, task: AgentTask, context: str) -> AgentResult:
        """One retry with half the scope."""
        reduced_scope = task.scope[: max(1, len(task.scope) // 2)]
        retry_task = AgentTask(
            task_id=f"{task.task_id}-retry",
            specialist_type=task.specialist_type,
            mission=task.mission,
            scope=reduced_scope,
            output_format=task.output_format,
            timeout_seconds=task.timeout_seconds,
        )
        try:
            result = await asyncio.wait_for(
                self._spawn_and_wait(retry_task, context),
                timeout=retry_task.timeout_seconds,
            )
            result.partial = True
            return result
        except Exception as e:
            log.warning("Retry also failed for %s: %s", task.task_id, e)
            return AgentResult(
                agent_id=task.task_id,
                specialist_type=task.specialist_type,
                success=False,
                summary=f"Failed after retry: {e}",
                partial=True,
            )

    async def _spawn_and_wait(self, task: AgentTask, context: str) -> AgentResult:
        """Spawn an agent subprocess and poll until it exits.

        For now this is a stub — real spawning uses agents.terminal.TerminalDetector
        and agents.registry.AgentRegistry when those are wired in. This returns a
        synthetic result so the planner/synthesizer chain works end-to-end.
        """
        # TODO: replace with real sub-agent spawn via TerminalDetector
        await asyncio.sleep(0.1)  # simulate async work
        return AgentResult(
            agent_id=task.task_id,
            specialist_type=task.specialist_type,
            success=True,
            summary=f"{task.specialist_type} completed: {task.mission[:60]}",
        )
