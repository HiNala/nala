from __future__ import annotations

import logging
import shlex
import subprocess
from pathlib import Path

from .registry import AgentHandle
from .terminal import SpawnStrategy

log = logging.getLogger(__name__)


class TmuxStrategy(SpawnStrategy):
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=check,
            timeout=15,
        )

    def _get_window_pid(self, window_name: str) -> int:
        try:
            res = self._run(
                ["tmux", "list-panes", "-t", window_name, "-F", "#{pane_pid}"],
            )
            val = res.stdout.strip().split("\n")[0]
            return int(val)
        except Exception:
            return -1

    def spawn_agent(self, agent_id: str, command: str, working_dir: str) -> AgentHandle:
        window_name = f"nala-{agent_id}"

        try:
            self._run(["tmux", "has-session"])
            has_session = True
        except subprocess.CalledProcessError:
            has_session = False

        if not has_session:
            self._run(["tmux", "new-session", "-d", "-s", "nala"])

        cmd_str = f"cd {shlex.quote(working_dir)} && exec {command}"
        self._run([
            "tmux",
            "new-window",
            "-n",
            window_name,
            "-d",
            cmd_str,
        ])

        pid = self._get_window_pid(window_name)

        return AgentHandle(
            agent_id=agent_id,
            pid=pid,
            strategy="tmux",
            window_name=window_name,
            working_dir=working_dir,
        )

    def send_input(self, handle: AgentHandle, text: str) -> None:
        if not handle.window_name:
            raise RuntimeError("No tmux window specified.")
        self._run(["tmux", "send-keys", "-t", handle.window_name, text, "Enter"])

    def get_output(self, handle: AgentHandle, lines: int = 50) -> str:
        if not handle.window_name:
            return "No window specified."
        try:
            result = self._run(
                ["tmux", "capture-pane", "-t", handle.window_name, "-p", "-S", f"-{lines}"],
                check=False,
            )
            return result.stdout.strip()
        except Exception as e:
            return f"Error capturing pane: {e}"

    def kill_agent(self, handle: AgentHandle) -> None:
        if not handle.window_name:
            return
        self._run(["tmux", "kill-window", "-t", handle.window_name], check=False)

    def is_alive(self, handle: AgentHandle) -> bool:
        if not handle.window_name:
            return False
        try:
            result = self._run(["tmux", "list-windows", "-F", "#{window_name}"], check=False)
        except Exception:
            return False
        return handle.window_name in result.stdout.splitlines()
