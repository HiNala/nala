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
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nala_orchestrator.chunking.embedder import Embedder
    from nala_orchestrator.config import Config
    from nala_orchestrator.models.router import ModelRouter

from .file_locks import FileLockRegistry
from .messages import MessageBus
from .task_list import SharedTaskList, Task

log = logging.getLogger(__name__)

# Hard wall on how long a single worker task may run before being cancelled.
_WORKER_TIMEOUT = 300  # seconds


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
        project_root: Path | None = None,
        embedder: Embedder | None = None,
        project_brief: str = "",
        model_override: tuple[str, str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.task = task
        self.config = config
        self._task_list = task_list
        self._locks = locks
        self._bus = bus
        self._project_root = project_root
        self._embedder = embedder
        self._project_brief = project_brief
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
            result = await asyncio.wait_for(
                self._execute(), timeout=_WORKER_TIMEOUT
            )
            self._task_list.complete_task(self.agent_id, self.task.id, result.summary)
        except asyncio.TimeoutError:
            result = WorkerResult(
                task_id=self.task.id,
                agent_id=self.agent_id,
                success=False,
                summary=f"Worker timed out after {_WORKER_TIMEOUT}s",
                files_touched=[],
            )
            self._task_list.fail_task(
                self.agent_id, self.task.id, result.summary
            )
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
        """Run the task using the full tool-calling loop.

        Workers use the same tool loop as the main agent so they can actually
        read, write, and edit files rather than just generating text.
        """
        from ..agent_runtime.tool_executor import run_tool_loop
        from ..agent_runtime.toolbox import Toolbox
        from ..agents.orchestrator import AgentOrchestrator
        from ..llm.provider import create_provider

        project_root = self._project_root or Path(".")
        agent = AgentOrchestrator(self.config, model_override=self._model_override)

        if self._embedder is not None and self._embedder.is_ready():
            agent.set_embedder(self._embedder)
        if self._project_root is not None:
            agent.context.project_root = str(self._project_root)

        toolbox = Toolbox(self.config, project_root, orchestrator=agent)

        # Build a rich scoped system prompt for the worker
        scope_desc = ", ".join(self.task.scope) if self.task.scope else "entire project"
        inbox = self._bus.format_for_agent(self.agent_id)
        prompt_parts = [
            f"You are worker agent **{self.agent_id}**, part of a multi-agent coding team.",
            "You have full tool access to read, write, edit, and run commands.",
            f"**Your scope:** {scope_desc}",
            f"**Project root:** {project_root}",
        ]
        if self._project_brief:
            prompt_parts.append(f"\n**Project context:** {self._project_brief[:400]}")
        if inbox:
            prompt_parts.append(f"\n**Messages from team:**\n{inbox}")
        prompt_parts += [
            "",
            "Use tools to explore and make changes. Always read files before editing.",
            "After completing your task, report: what you changed, where, and the outcome.",
        ]
        system_prompt = "\n".join(prompt_parts)

        try:
            provider = create_provider(self.config)
        except Exception as exc:
            raise RuntimeError(f"Could not create LLM provider: {exc}") from exc

        chunks: list[str] = []
        try:
            async for chunk in run_tool_loop(
                provider=provider,
                toolbox=toolbox,
                system_prompt=system_prompt,
                user_message=self.task.objective,
                max_rounds=15,
                max_tokens=4096,
            ):
                chunks.append(chunk)
        except Exception as e:
            raise RuntimeError(f"Worker tool loop failed: {e}") from e

        full_response = "".join(chunks)

        # Determine which files were actually touched by checking git diff
        files_touched = list(self.task.scope)
        try:
            diff_out = toolbox.git_diff()
            if diff_out and "no changes" not in diff_out:
                import re
                touched = re.findall(r"^diff --git a/.+ b/(.+)$", diff_out, re.MULTILINE)
                if touched:
                    files_touched = touched
        except Exception:
            pass

        success = bool(full_response.strip()) and "(tool error" not in full_response.lower()
        return WorkerResult(
            task_id=self.task.id,
            agent_id=self.agent_id,
            success=success,
            summary=full_response[:800],
            files_touched=files_touched,
        )


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
        project_root: Path | None = None,
        embedder: Embedder | None = None,
        project_brief: str = "",
    ) -> None:
        self._config = config
        self._task_list = task_list
        self._locks = locks
        self._bus = bus
        self._max_concurrent = max_concurrent
        self._router = model_router
        self._project_root = project_root
        self._embedder = embedder
        self._project_brief = project_brief
        self._agent_counter = 0

    def set_embedder(self, embedder: Embedder) -> None:
        """Update the embedder reference (called after index rebuild)."""
        self._embedder = embedder

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
                project_root=self._project_root,
                embedder=self._embedder,
                project_brief=self._project_brief,
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
