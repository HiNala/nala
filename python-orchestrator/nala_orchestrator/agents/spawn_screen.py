from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from .registry import AgentHandle
from .terminal import SpawnStrategy

log = logging.getLogger(__name__)


class ScreenStrategy(SpawnStrategy):
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.logs_dir = workspace_root / ".nala" / "agents"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            check=check,
            timeout=15,
        )

    def _get_session_pid(self, session_name: str) -> int:
        try:
            result = self._run("screen", "-ls", check=False)
        except Exception:
            return -1
        pattern = re.compile(rf"\s*(\d+)\.{re.escape(session_name)}\s")
        for line in result.stdout.splitlines():
            match = pattern.search(line)
            if match:
                return int(match.group(1))
        return -1

    def spawn_agent(self, agent_id: str, command: str, working_dir: str) -> AgentHandle:
        session_name = f"nala-{agent_id}"
        log_file = self.logs_dir / f"{agent_id}.log"
        subprocess.run(
            [
                "screen",
                "-L",
                "-Logfile",
                str(log_file),
                "-dmS",
                session_name,
                "bash",
                "-lc",
                f"cd {working_dir!r} && exec {command}",
            ],
            check=True,
            timeout=15,
        )
        return AgentHandle(
            agent_id=agent_id,
            pid=self._get_session_pid(session_name),
            strategy="screen",
            window_name=session_name,
            log_file=str(log_file),
        )

    def send_input(self, handle: AgentHandle, text: str) -> None:
        if not handle.window_name:
            raise RuntimeError("No screen session specified.")
        subprocess.run(
            ["screen", "-S", handle.window_name, "-X", "stuff", f"{text}\n"],
            check=True,
            timeout=15,
        )

    def get_output(self, handle: AgentHandle, lines: int = 50) -> str:
        if not handle.log_file:
            return f"No log file found for agent {handle.agent_id}."
        log_path = Path(handle.log_file)
        if not log_path.exists():
            return f"No log file found for agent {handle.agent_id}."
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return f"Error reading log file: {exc}"
        return "\n".join(content[-lines:])

    def kill_agent(self, handle: AgentHandle) -> None:
        if not handle.window_name:
            return
        subprocess.run(
            ["screen", "-S", handle.window_name, "-X", "quit"],
            check=False,
            timeout=15,
        )

    def is_alive(self, handle: AgentHandle) -> bool:
        if not handle.window_name:
            return False
        try:
            result = self._run("screen", "-ls", handle.window_name, check=False)
        except Exception:
            return False
        return handle.window_name in result.stdout
