"""Worker agent spawner.

Creates worker agent instances that run as asyncio tasks, each with
their own LLM session, scoped context, and tool permissions.

Workers report their results through the shared task list, not directly
to the lead — keeping coordination decoupled (open-multi-agent pattern).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nala_orchestrator.config import Config
    from nala_orchestrator.models.router import ModelRouter

from .file_locks import FileLockRegistry
from .messages import MessageBus
from .task_list import SharedTaskList, Task

log = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    """The outcome reported by a worker agent."""
    task_id: str
    agent_id: str
    success: bool
    summary: str
    files_touched: list[str]


class WorkerAgent:
    """A scoped agent running one task in its own asyncio context."""

    def __init__(
        self,
        agent_id: str,
        task: Task,
        config: Config,
        task_list: SharedTaskList,
        locks: FileLockRegistry,
        bus: MessageBus,
        model_override: tuple[str, str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.task = task
        self.config = config
        self._task_list = task_list
        self._locks = locks
        self._bus = bus
        self._model_override = model_override

    async def run(self) -> WorkerResult:
        """Execute the task and report back through the task list."""
        if not self._task_list.claim_task(self.agent_id, self.task.id):
            return WorkerResult(
                task_id=self.task.id,
                agent_id=self.agent_id,
                success=False,
                summary="Could not claim task (already taken)",
                files_touched=[],
            )

        # Acquire file locks for scoped files
        acquired: list[str] = []
        for fp in self.task.scope:
            if not self._locks.acquire(self.agent_id, fp):
                holder = self._locks.holder(fp)
                log.warning("Agent %s: file %s locked by %s", self.agent_id, fp, holder)
            else:
                acquired.append(fp)

        try:
            result = await self._execute()
            self._task_list.complete_task(self.agent_id, self.task.id, result.summary)
        except Exception as e:
            result = WorkerResult(
                task_id=self.task.id,
                agent_id=self.agent_id,
                success=False,
                summary=f"Error: {e}",
                files_touched=[],
            )
            self._task_list.fail_task(self.agent_id, self.task.id, str(e))
        finally:
            for fp in acquired:
                self._locks.release(self.agent_id, fp)

        return result

    async def _execute(self) -> WorkerResult:
        """Run the actual LLM call for this task."""
        from ..agents.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator(self.config, model_override=self._model_override)

        # Inject pending messages
        inbox = self._bus.format_for_agent(self.agent_id)
        if inbox:
            agent.context.inject_system(inbox)

        # Scoped system injection
        scope_desc = ", ".join(self.task.scope) or "entire project"
        agent.context.inject_system(
            f"[WORKER AGENT {self.agent_id}]\n"
            f"Scope: {scope_desc}\n"
            f"Objective: {self.task.objective}\n"
            "[Focus only on the above scope. Report findings concisely.]"
        )

        try:
            response = await agent.query(self.task.objective)
            return WorkerResult(
                task_id=self.task.id,
                agent_id=self.agent_id,
                success=True,
                summary=response[:500],
                files_touched=self.task.scope,
            )
        except Exception as e:
            raise RuntimeError(f"Worker LLM call failed: {e}") from e


class AgentSpawner:
    """Spawns and runs worker agents for a task wave."""

    def __init__(
        self,
        config: Config,
        task_list: SharedTaskList,
        locks: FileLockRegistry,
        bus: MessageBus,
        max_concurrent: int = 3,
        model_router: ModelRouter | None = None,
    ) -> None:
        self._config = config
        self._task_list = task_list
        self._locks = locks
        self._bus = bus
        self._max_concurrent = max_concurrent
        self._agent_counter = 0
        self._router = model_router

    def _resolve_model(self) -> tuple[str, str] | None:
        """Use the router to pick a coding model for workers."""
        if self._router is None:
            return None
        try:
            from nala_orchestrator.models.types import TaskType
            result = self._router.route(TaskType.CODE)
            return (result.provider.value, result.model_id)
        except Exception:
            return None

    async def run_wave(self, tasks: list[Task]) -> list[WorkerResult]:
        """Run a list of tasks in parallel up to max_concurrent."""
        semaphore = asyncio.Semaphore(self._max_concurrent)
        model_override = self._resolve_model()

        async def run_one(task: Task) -> WorkerResult:
            self._agent_counter += 1
            agent_id = f"worker-{self._agent_counter}"
            worker = WorkerAgent(
                agent_id=agent_id,
                task=task,
                config=self._config,
                task_list=self._task_list,
                locks=self._locks,
                bus=self._bus,
                model_override=model_override,
            )
            async with semaphore:
                log.info(
                    "Worker %s starting task: %s (model: %s)",
                    agent_id,
                    task.objective[:50],
                    f"{model_override[0]}/{model_override[1]}" if model_override else "default",
                )
                result = await worker.run()
                log.info(
                    "Worker %s finished: %s (%s)",
                    agent_id, "OK" if result.success else "FAIL", task.id,
                )
                return result

        aws = [run_one(t) for t in tasks]
        results = list(await asyncio.gather(*aws, return_exceptions=False))
        return results
