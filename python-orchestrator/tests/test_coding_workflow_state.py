from pathlib import Path

from nala_orchestrator.agents.actions import EditAction
from nala_orchestrator.agents.orchestrator import AgentOrchestrator
from nala_orchestrator.cli import _get_action_executor
from nala_orchestrator.config import Config


def test_build_system_prompt_includes_background_summary(tmp_path: Path) -> None:
    config = Config.load(project_root=tmp_path)
    agent = AgentOrchestrator(config)
    history = [
        {"role": "user", "content": "Refactor the auth module."},
        {"role": "assistant", "content": "Applied auth cleanup."},
        {"role": "user", "content": "Now add tests."},
    ]
    agent._bg_summary.force_rebuild(history)

    prompt = agent.build_system_prompt("auth")

    assert "[SESSION SUMMARY]" in prompt
    assert "Refactor the auth module." in prompt
    assert "Current task: Now add tests." in prompt


def test_shared_action_executor_persists_across_calls(tmp_path: Path) -> None:
    file_path = tmp_path / "example.py"
    file_path.write_text("print('old')\n", encoding="utf-8")

    first = _get_action_executor(tmp_path, reset=True)
    action = EditAction(
        file_path="example.py",
        old_content="print('old')",
        new_content="print('new')",
        description="Update example output",
    )
    result = first.apply(action)
    second = _get_action_executor(tmp_path)

    assert result.success
    assert first is second
    assert second._applied == 1


def test_project_env_overrides_home_env(monkeypatch, tmp_path: Path) -> None:
    home_dir = tmp_path / "fake-home"
    home_nala = home_dir / ".nala"
    home_nala.mkdir(parents=True)
    (home_nala / ".env").write_text(
        "LLM_PROVIDER=anthropic\nOPENAI_API_KEY=home-key\nDASHBOARD_PORT=9000\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=openai\nOPENAI_API_KEY=project-key\nDASHBOARD_PORT=4567\n",
        encoding="utf-8",
    )

    for key in ("LLM_PROVIDER", "OPENAI_API_KEY", "DASHBOARD_PORT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    config = Config.load(project_root=tmp_path)

    assert config.llm_provider == "openai"
    assert config.openai_api_key == "project-key"
    assert config.dashboard_port == 4567
