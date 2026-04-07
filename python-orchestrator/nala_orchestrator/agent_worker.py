"""Entry point for standalone worker agents running in dedicated terminals."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .agent_runtime.tool_executor import run_tool_loop
from .agent_runtime.toolbox import Toolbox
from .agents.orchestrator import AgentOrchestrator
from .config import load_config
from .llm.provider import create_provider
from .multi_agent.file_locks import FileLockRegistry
from .multi_agent.task_list import SharedTaskList

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


async def run_worker(agent_id: str, task_id: str, project_root: str) -> None:
    root = Path(project_root)
    config = load_config(root)

    task_list = SharedTaskList(root)
    locks = FileLockRegistry()

    task = task_list.get_task(task_id)
    if not task:
        log.error("Task %s not found.", task_id)
        return

    acquired: list[str] = []
    for fp in task.scope:
        if not locks.acquire(agent_id, fp):
            log.warning("Agent %s: file %s locked.", agent_id, fp)
        else:
            acquired.append(fp)

    try:
        agent = AgentOrchestrator(config)
        agent.context.project_root = str(root)
        toolbox = Toolbox(config, root, orchestrator=agent)

        scope_desc = ", ".join(task.scope) if task.scope else "entire project"
        prompt_parts = [
            f"You are worker agent **{agent_id}**, part of a multi-agent coding team.",
            "You have full tool access to read, write, edit, and run commands.",
            f"**Your scope:** {scope_desc}",
            f"**Project root:** {root}",
        ]
        prompt_parts += [
            "",
            "Use tools to explore and make changes. Always read files before editing.",
            "After completing your task, report: what you changed, where, and the outcome.",
        ]
        system_prompt = "\n".join(prompt_parts)

        provider = create_provider(config)

        chunks: list[str] = []
        async for chunk in run_tool_loop(
            provider=provider,
            toolbox=toolbox,
            system_prompt=system_prompt,
            user_message=task.objective,
            max_rounds=15,
            max_tokens=4096,
        ):
            sys.stdout.write(chunk)
            sys.stdout.flush()
            chunks.append(chunk)

        full_response = "".join(chunks)
        task_list.complete_task(agent_id, task_id, full_response[:800])
        log.info("Task %s completed successfully.", task_id)

    except Exception as e:
        task_list.fail_task(agent_id, task_id, str(e))
        log.error("Worker failed: %s", e)
    finally:
        for fp in acquired:
            locks.release(agent_id, fp)


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Agent Worker")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()

    asyncio.run(run_worker(args.agent_id, args.task_id, args.root))

if __name__ == "__main__":
    main()
