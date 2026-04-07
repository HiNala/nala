from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from nala_orchestrator.agents.registry import AgentRegistry
from nala_orchestrator.agents.terminal import TerminalDetector


def _python_shell_command(code: str) -> str:
    args = [sys.executable, "-c", code]
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def test_terminal_detector_falls_back_to_subprocess_when_no_multiplexer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("STY", raising=False)
    monkeypatch.setattr("nala_orchestrator.agents.terminal.shutil.which", lambda _: None)

    strategy = TerminalDetector.get_strategy(tmp_path)

    assert strategy.__class__.__name__ == "SubprocessStrategy"


def test_subprocess_strategy_spawns_and_tails_output(tmp_path: Path) -> None:
    strategy = TerminalDetector.get_strategy_for_handle(
        tmp_path,
        type("Handle", (), {"strategy": "subprocess"})(),
    )
    handle = strategy.spawn_agent(
        agent_id="worker-subprocess",
        command=_python_shell_command(
            "import time; print('hello from worker', flush=True); time.sleep(0.2)"
        ),
        working_dir=str(tmp_path),
    )

    deadline = time.time() + 5
    output = ""
    while time.time() < deadline:
        output = strategy.get_output(handle, 20)
        if "hello from worker" in output:
            break
        time.sleep(0.1)

    assert "hello from worker" in output

    wait_deadline = time.time() + 5
    while time.time() < wait_deadline and strategy.is_alive(handle):
        time.sleep(0.1)

    assert not strategy.is_alive(handle)


def test_agent_registry_persists_and_cleans_up_dead_processes(tmp_path: Path) -> None:
    strategy = TerminalDetector.get_strategy_for_handle(
        tmp_path,
        type("Handle", (), {"strategy": "subprocess"})(),
    )
    handle = strategy.spawn_agent(
        agent_id="worker-registry",
        command=_python_shell_command("print('done', flush=True)"),
        working_dir=str(tmp_path),
    )

    registry = AgentRegistry(tmp_path)
    registry.register(handle)
    assert registry.get_agent("worker-registry") is not None

    deadline = time.time() + 5
    while time.time() < deadline and registry.is_alive("worker-registry"):
        time.sleep(0.1)

    reloaded = AgentRegistry(tmp_path)

    assert reloaded.get_agent("worker-registry") is None
