from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from .registry import AgentHandle, AgentRegistry
from .terminal import TerminalDetector


def build_worker_command(agent_id: str, task_id: str, project_root: Path) -> str:
    args = [
        sys.executable,
        "-m",
        "nala_orchestrator.agent_worker",
        "--agent-id",
        agent_id,
        "--task-id",
        task_id,
        "--root",
        str(project_root.resolve()),
    ]
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def spawn_registered_worker(
    project_root: Path,
    agent_id: str,
    task_id: str,
) -> AgentHandle:
    strategy = TerminalDetector.get_strategy(project_root)
    handle = strategy.spawn_agent(
        agent_id=agent_id,
        command=build_worker_command(agent_id, task_id, project_root),
        working_dir=str(project_root),
    )
    AgentRegistry(project_root).register(handle)
    return handle
