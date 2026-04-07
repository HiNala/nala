from __future__ import annotations

import logging
import os
import signal
import subprocess
from pathlib import Path

from .registry import AgentHandle
from .terminal import SpawnStrategy

log = logging.getLogger(__name__)


class SubprocessStrategy(SpawnStrategy):
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.logs_dir = workspace_root / ".nala" / "agents"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def spawn_agent(self, agent_id: str, command: str, working_dir: str) -> AgentHandle:
        log_file = self.logs_dir / f"{agent_id}.log"
        try:
            cmd_file = log_file.open("w", encoding="utf-8")
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=working_dir,
                stdout=cmd_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            return AgentHandle(
                agent_id=agent_id,
                pid=process.pid,
                strategy="subprocess",
                log_file=str(log_file),
                working_dir=working_dir,
            )
        except Exception as e:
            log.error("Failed to spawn subprocess agent %s: %s", agent_id, e)
            raise

    def send_input(self, handle: AgentHandle, text: str) -> None:
        del handle, text
        raise RuntimeError(
            "Interactive input is not supported for subprocess-backed agents. "
            "Use tmux or screen for live interaction."
        )

    def get_output(self, handle: AgentHandle, lines: int = 50) -> str:
        if not handle.log_file or not Path(handle.log_file).exists():
            return f"No log file found for agent {handle.agent_id}."
        
        try:
            with Path(handle.log_file).open("r", encoding="utf-8") as f:
                content = f.read().splitlines()
                return "\n".join(content[-lines:])
        except Exception as e:
            msg = f"Error reading log file: {e}"
            log.warning(msg)
            return msg

    def kill_agent(self, handle: AgentHandle) -> None:
        try:
            from .registry import _psutil

            if _psutil is not None:
                p = _psutil.Process(handle.pid)
                p.terminate()
                try:
                    p.wait(timeout=3)
                except _psutil.TimeoutExpired:
                    p.kill()
                return
            # psutil not available — use os.kill with SIGTERM
            try:
                os.kill(handle.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        except Exception as e:
            log.error("Failed to kill agent process %s: %s", handle.pid, e)

    def is_alive(self, handle: AgentHandle) -> bool:
        try:
            from .registry import _psutil

            if _psutil is not None:
                process = _psutil.Process(handle.pid)
                return process.status() != _psutil.STATUS_ZOMBIE
            import os

            os.kill(handle.pid, 0)
            return True
        except (OSError, ProcessLookupError):
            pass
        except Exception:
            pass
        return False
