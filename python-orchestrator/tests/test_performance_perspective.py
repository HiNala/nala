from pathlib import Path

import pytest

from nala_orchestrator.config import Config
from nala_orchestrator.perspectives.performance import PerformancePerspective


@pytest.mark.asyncio
async def test_performance_detects_nested_loop(tmp_path: Path) -> None:
    src = tmp_path / "sample.py"
    src.write_text("for i in items: for j in items: print(i, j)\n", encoding="utf-8")

    cfg = Config.load(project_root=tmp_path)
    perspective = PerformancePerspective(cfg, graph=None)
    result = await perspective.analyze(str(tmp_path))

    assert result.perspective_name == "performance"
    assert any("nested loop" in f.title.lower() for f in result.findings)
