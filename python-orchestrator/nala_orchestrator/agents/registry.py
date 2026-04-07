from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import psutil as _psutil
except ImportError:  # psutil optional — fall back to os.kill
    _psutil = None  # type: ignore

log = logging.getLogger(__name__)


@dataclass
class AgentHandle:
    agent_id: str
    pid: int
    strategy: str
    task_id: str = ""
    window_name: str | None = None
    log_file: str | None = None
    status: str = "running"
    objective: str = ""
    working_dir: str = ""


class AgentRegistry:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.agents_dir = workspace_root / ".nala" / "agents"
        self.registry_file = self.agents_dir / "registry.json"

        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.agents: dict[str, AgentHandle] = {}
        self._load()
        self.cleanup_dead()

    def _load(self) -> None:
        if not self.registry_file.exists():
            return
        try:
            with self.registry_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return
                for agent_id, info in data.items():
                    if isinstance(info, dict):
                        self.agents[agent_id] = AgentHandle(**info)
        except Exception as e:
            log.warning("Failed to load agent registry: %s", e)

    def _save(self) -> None:
        try:
            with self.registry_file.open("w", encoding="utf-8") as f:
                data = {aid: asdict(handle) for aid, handle in self.agents.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            log.warning("Failed to save agent registry: %s", e)

    def register(self, handle: AgentHandle) -> None:
        self.agents[handle.agent_id] = handle
        self._save()

    def unregister(self, agent_id: str) -> None:
        if agent_id in self.agents:
            del self.agents[agent_id]
            self._save()

    def get_agent(self, agent_id: str) -> AgentHandle | None:
        return self.agents.get(agent_id)

    def get_active(self) -> list[AgentHandle]:
        return [a for a in self.agents.values() if self.is_alive(a.agent_id)]

    def update(self, agent_id: str, **changes: Any) -> AgentHandle | None:
        handle = self.agents.get(agent_id)
        if handle is None:
            return None
        for key, value in changes.items():
            if hasattr(handle, key):
                setattr(handle, key, value)
        self._save()
        return handle

    def is_alive(self, agent_id: str) -> bool:
        agent = self.agents.get(agent_id)
        if not agent:
            return False

        if agent.status not in {"running", "pending"}:
            return False
        if agent.pid <= 0:
            return False

        if agent.strategy in {"tmux", "screen"} and agent.window_name:
            try:
                from .terminal import TerminalDetector

                strategy = TerminalDetector.get_strategy_for_handle(self.workspace_root, agent)
                return strategy.is_alive(agent)
            except Exception:
                return False

        try:
            if _psutil is not None:
                p = _psutil.Process(agent.pid)
                return p.status() != _psutil.STATUS_ZOMBIE
            else:
                # Fallback: os.kill(pid, 0) raises OSError if the process is gone
                os.kill(agent.pid, 0)
                return True
        except (OSError, ProcessLookupError):
            return False
        except Exception:
            return False

    def cleanup_dead(self) -> None:
        removed = False
        for agent_id in list(self.agents.keys()):
            if not self.is_alive(agent_id):
                del self.agents[agent_id]
                removed = True

        if removed:
            self._save()
