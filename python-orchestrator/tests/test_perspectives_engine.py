from pathlib import Path

import pytest

from nala_orchestrator.config import Config
from nala_orchestrator.perspectives.engine import PerspectivesEngine


@pytest.mark.asyncio
async def test_engine_includes_new_perspectives(tmp_path: Path) -> None:
    cfg = Config.load(project_root=tmp_path)
    engine = PerspectivesEngine(cfg, graph=None)
    names = engine.perspective_names()
    assert "churn" in names
    assert "performance" in names
