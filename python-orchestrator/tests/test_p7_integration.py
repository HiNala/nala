"""Integration tests for Phase 7: settings → registry → router → orchestrator chain.

These tests verify the integration layer works end-to-end without
requiring live API keys. They use mocked responses to simulate the
full flow.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# ── Settings chain tests ──────────────────────────────────────────────


def test_settings_schema_defaults():
    """NalaSettings has sensible defaults for all sections."""
    from nala_orchestrator.settings.schema import NalaSettings

    s = NalaSettings()
    assert s.keys.anthropic_api_key == ""
    assert s.models.default_provider == "anthropic"
    assert s.models.default_model == "claude-sonnet-4-6"
    assert s.agent.autonomy == "guided"
    assert s.agent.max_workers == 3
    assert s.agent.git.auto_branch is True
    assert s.display.theme == "dark"


def test_settings_routing_as_overrides():
    """ModelRoutingSettings.as_overrides parses slash and colon separators."""
    from nala_orchestrator.settings.schema import ModelRoutingSettings

    r = ModelRoutingSettings(
        plan="anthropic/claude-opus-4-6",
        code="openai:gpt-4o",
        explore="",
    )
    overrides = r.as_overrides()
    assert overrides["plan"] == ("anthropic", "claude-opus-4-6")
    assert overrides["code"] == ("openai", "gpt-4o")
    assert "explore" not in overrides


def test_settings_format_summary():
    """NalaSettings.format_summary produces readable output."""
    from nala_orchestrator.settings.schema import NalaSettings, KeysSettings

    s = NalaSettings(keys=KeysSettings(anthropic_api_key="sk-test"))
    summary = s.format_summary()
    assert "Anthropic" in summary
    assert "configured" in summary
    assert "guided" in summary


def test_settings_writer_roundtrip():
    """Write settings and read them back."""
    from nala_orchestrator.settings.schema import NalaSettings, KeysSettings, ModelsSettings
    from nala_orchestrator.settings.writer import SettingsWriter
    from nala_orchestrator.settings.loader import SettingsLoader

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        nala_dir = root / ".nala"
        nala_dir.mkdir()
        path = nala_dir / "settings.toml"

        original = NalaSettings(
            keys=KeysSettings(anthropic_api_key="sk-test-123"),
            models=ModelsSettings(default_provider="openai", default_model="gpt-4o"),
        )
        writer = SettingsWriter(path)
        writer.write(original)

        assert path.exists()

        # Isolate from real env vars that would override TOML values
        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "LLM_PROVIDER")
        }
        with patch.dict(os.environ, clean_env, clear=True):
            loader = SettingsLoader(root)
            loaded = loader.load()
            assert loaded.keys.anthropic_api_key == "sk-test-123"
            assert loaded.models.default_provider == "openai"
            assert loaded.models.default_model == "gpt-4o"


def test_settings_set_value_persists():
    """SettingsWriter.set_value changes a value and persists."""
    from nala_orchestrator.settings.schema import NalaSettings
    from nala_orchestrator.settings.writer import SettingsWriter

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "settings.toml"
        s = NalaSettings()
        writer = SettingsWriter(path)

        msg = writer.set_value("agent.autonomy", "autonomous", s)
        assert "autonomous" in msg
        assert s.agent.autonomy == "autonomous"
        assert path.exists()


def test_settings_set_value_unknown_key():
    from nala_orchestrator.settings.schema import NalaSettings
    from nala_orchestrator.settings.writer import SettingsWriter

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "settings.toml"
        s = NalaSettings()
        writer = SettingsWriter(path)
        msg = writer.set_value("nonexistent.key", "value", s)
        assert "Unknown" in msg


def test_settings_env_override():
    """Environment variables override settings.toml values."""
    from nala_orchestrator.settings.schema import NalaSettings, KeysSettings
    from nala_orchestrator.settings.writer import SettingsWriter
    from nala_orchestrator.settings.loader import SettingsLoader

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        nala_dir = root / ".nala"
        nala_dir.mkdir()
        path = nala_dir / "settings.toml"

        toml_settings = NalaSettings(
            keys=KeysSettings(anthropic_api_key="toml-key"),
        )
        SettingsWriter(path).write(toml_settings)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            loaded = SettingsLoader(root).load()
            assert loaded.keys.anthropic_api_key == "env-key"


def test_config_loads_settings_toml():
    """Config.load reads from settings.toml when it exists."""
    from nala_orchestrator.settings.schema import NalaSettings, ModelsSettings
    from nala_orchestrator.settings.writer import SettingsWriter

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        nala_dir = root / ".nala"
        nala_dir.mkdir()
        path = nala_dir / "settings.toml"

        toml_settings = NalaSettings(
            models=ModelsSettings(default_provider="openai", default_model="gpt-4o"),
        )
        SettingsWriter(path).write(toml_settings)

        env_clean = {
            k: v for k, v in os.environ.items()
            if k not in ("LLM_PROVIDER", "OPENAI_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY")
        }
        with patch.dict(os.environ, env_clean, clear=True):
            from nala_orchestrator.config import Config
            config = Config.load(project_root=root)
            assert config.llm_provider == "openai"


# ── Model types and routing tests ─────────────────────────────────────


def test_model_info_strength_score():
    """ModelInfo.strength_score returns higher scores for matching tasks."""
    from nala_orchestrator.models.types import (
        CostTier, ModelInfo, Provider, TaskType,
    )

    model = ModelInfo(
        id="test-model",
        display_name="Test",
        provider=Provider.ANTHROPIC,
        context_window=100_000,
        max_output=4096,
        cost_tier=CostTier.EXPENSIVE,
        strengths=frozenset({"planning", "reasoning"}),
        recommended_tasks=frozenset({TaskType.PLAN}),
    )
    plan_score = model.strength_score(TaskType.PLAN)
    code_score = model.strength_score(TaskType.CODE)
    assert plan_score > code_score


def test_task_type_values():
    """All expected task types exist."""
    from nala_orchestrator.models.types import TaskType
    expected = {"plan", "code", "explore", "research", "design", "review", "summarize"}
    actual = {t.value for t in TaskType}
    assert expected == actual


def test_catalog_has_all_providers():
    """Bundled catalog has models for all four providers."""
    from nala_orchestrator.models.catalog import BUNDLED_CATALOG
    from nala_orchestrator.models.types import Provider

    for p in Provider:
        assert p in BUNDLED_CATALOG, f"Missing catalog for {p.value}"
        assert len(BUNDLED_CATALOG[p]) > 0, f"Empty catalog for {p.value}"


# ── Mission writer / executor tests ───────────────────────────────────


def test_mission_writer_parse_json():
    """MissionWriter.parse_plan_output handles JSON arrays."""
    from nala_orchestrator.agent_runtime.mission_writer import MissionWriter

    raw = json.dumps([
        {
            "id": "mission-1",
            "title": "Setup",
            "objective": "Set up project",
            "task_type": "code",
            "dependencies": [],
            "steps": ["Init project", "Add deps"],
            "acceptance_criteria": ["Project compiles"],
        },
        {
            "id": "mission-2",
            "title": "Implement",
            "objective": "Build feature",
            "task_type": "code",
            "dependencies": ["mission-1"],
            "steps": ["Write code"],
            "acceptance_criteria": ["Feature works"],
        },
    ])

    missions = MissionWriter.parse_plan_output(raw)
    assert len(missions) == 2
    assert missions[0].id == "mission-1"
    assert missions[1].dependencies == ["mission-1"]


def test_mission_writer_parse_markdown():
    """MissionWriter.parse_plan_output handles markdown format."""
    from nala_orchestrator.agent_runtime.mission_writer import MissionWriter

    raw = """
# Mission: Setup project
## Objective
Initialize the project structure
## Task Type
code
## Steps
1. Create directory
2. Add package.json
## Acceptance Criteria
- Project structure exists

# Mission: Build feature
## Objective
Implement the main feature
## Task Type
code
## Dependencies
- mission-1
## Steps
1. Write implementation
"""
    missions = MissionWriter.parse_plan_output(raw)
    assert len(missions) >= 2


def test_mission_writer_roundtrip():
    """Write missions and load them back."""
    from nala_orchestrator.agent_runtime.mission_writer import MissionWriter
    from nala_orchestrator.agent_runtime.state import MissionFile, MissionStatus

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        writer = MissionWriter(root, "test-run-1")

        missions = [
            MissionFile(
                id="m-1", title="First", objective="Do first thing",
                task_type="code", steps=["Step 1"],
                acceptance_criteria=["Criterion 1"],
            ),
            MissionFile(
                id="m-2", title="Second", objective="Do second thing",
                task_type="review", dependencies=["m-1"],
                steps=["Step 2"],
            ),
        ]
        paths = writer.write_missions(missions)
        assert len(paths) == 2

        loaded = writer.load_missions()
        assert len(loaded) == 2
        assert loaded[0].id == "m-1"
        assert loaded[1].dependencies == ["m-1"]


def test_mission_status_update():
    """Updating mission status persists to manifest."""
    from nala_orchestrator.agent_runtime.mission_writer import MissionWriter
    from nala_orchestrator.agent_runtime.state import MissionFile, MissionStatus

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        writer = MissionWriter(root, "test-run-2")
        missions = [
            MissionFile(id="m-1", title="Test", objective="Test obj"),
        ]
        writer.write_missions(missions)
        writer.update_mission_status("m-1", MissionStatus.COMPLETED, "All good")

        loaded = writer.load_missions()
        assert loaded[0].status == MissionStatus.COMPLETED
        assert loaded[0].result_summary == "All good"


def test_executor_dependency_resolution():
    """MissionExecutor._get_ready_missions resolves dependencies."""
    from nala_orchestrator.agent_runtime.executor import MissionExecutor
    from nala_orchestrator.agent_runtime.state import MissionFile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        m1 = MissionFile(id="m-1", title="First", objective="First")
        m2 = MissionFile(id="m-2", title="Second", objective="Second", dependencies=["m-1"])
        m3 = MissionFile(id="m-3", title="Third", objective="Third", dependencies=["m-1"])

        from unittest.mock import MagicMock
        config = MagicMock()
        config.project_root = root
        config.session_dir_name = ".nala"
        executor = MissionExecutor(config, root, "test-run")

        pending = {"m-1": m1, "m-2": m2, "m-3": m3}
        ready = executor._get_ready_missions(pending, set())
        assert len(ready) == 1
        assert ready[0].id == "m-1"

        ready2 = executor._get_ready_missions(pending, {"m-1"})
        assert len(ready2) == 3  # all ready now


def test_executor_parallel_grouping():
    """MissionExecutor._group_parallel groups correctly."""
    from nala_orchestrator.agent_runtime.executor import MissionExecutor
    from nala_orchestrator.agent_runtime.state import MissionFile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        m1 = MissionFile(id="m-1", title="A", objective="A", parallel_group="group-a")
        m2 = MissionFile(id="m-2", title="B", objective="B", parallel_group="group-a")
        m3 = MissionFile(id="m-3", title="C", objective="C", parallel_group="sequential")

        from unittest.mock import MagicMock
        config = MagicMock()
        executor = MissionExecutor(config, root, "test-run")

        groups = executor._group_parallel([m1, m2, m3])
        assert "group-a" in groups
        assert len(groups["group-a"]) == 2
        seq_groups = [k for k in groups if k.startswith("_seq_")]
        assert len(seq_groups) == 1


def test_friendly_error_messages():
    """_friendly_error returns actionable messages for common errors."""
    from nala_orchestrator.agent_runtime.executor import _friendly_error

    assert "API key" in _friendly_error(Exception("401 Unauthorized"))
    assert "Rate limited" in _friendly_error(Exception("429 Too Many Requests"))
    assert "timed out" in _friendly_error(Exception("Request timed out"))
    assert "network" in _friendly_error(Exception("Connection refused"))
