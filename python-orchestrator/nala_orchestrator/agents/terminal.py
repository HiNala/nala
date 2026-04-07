from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from .registry import AgentHandle


class SpawnStrategy(ABC):
    @abstractmethod
    def spawn_agent(self, agent_id: str, command: str, working_dir: str) -> AgentHandle:
        raise NotImplementedError

    @abstractmethod
    def send_input(self, handle: AgentHandle, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_output(self, handle: AgentHandle, lines: int = 50) -> str:
        raise NotImplementedError

    @abstractmethod
    def kill_agent(self, handle: AgentHandle) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_alive(self, handle: AgentHandle) -> bool:
        raise NotImplementedError


class TerminalDetector:
    @staticmethod
    def get_strategy(workspace_root: Path) -> SpawnStrategy:
        from .spawn_subprocess import SubprocessStrategy
        from .spawn_screen import ScreenStrategy
        from .spawn_tmux import TmuxStrategy

        tmux_available = shutil.which("tmux") is not None
        screen_available = shutil.which("screen") is not None

        if os.environ.get("TMUX") and tmux_available:
            return TmuxStrategy(workspace_root)
        if os.environ.get("STY") and screen_available:
            return ScreenStrategy(workspace_root)
        if tmux_available:
            return TmuxStrategy(workspace_root)
        if screen_available:
            return ScreenStrategy(workspace_root)
        return SubprocessStrategy(workspace_root)

    @staticmethod
    def get_strategy_for_handle(workspace_root: Path, handle: AgentHandle) -> SpawnStrategy:
        from .spawn_subprocess import SubprocessStrategy
        from .spawn_screen import ScreenStrategy
        from .spawn_tmux import TmuxStrategy

        if handle.strategy == "tmux":
            return TmuxStrategy(workspace_root)
        if handle.strategy == "screen":
            return ScreenStrategy(workspace_root)
        return SubprocessStrategy(workspace_root)
