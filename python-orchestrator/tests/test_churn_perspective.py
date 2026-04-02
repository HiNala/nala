from pathlib import Path

import pytest

from nala_orchestrator.config import Config
from nala_orchestrator.perspectives.churn import ChurnPerspective


@pytest.mark.asyncio
async def test_churn_handles_non_git_directory(tmp_path: Path) -> None:
    cfg = Config.load(project_root=tmp_path)
    perspective = ChurnPerspective(cfg, graph=None)
    result = await perspective.analyze(str(tmp_path))
    assert result.perspective_name == "churn"
    assert "skipped" in result.summary.lower()
