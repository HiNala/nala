"""Tests for the pre-analysis chunking strategies (Mission 08)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nala_orchestrator.perspectives.chunking import (
    AnalysisSection,
    chunk_by_complexity,
    chunk_by_directory,
    chunk_by_module,
)


@pytest.fixture()
def sample_project(tmp_path: Path) -> Path:
    """Create a small fake project tree."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def foo():\n  pass\n")
    (tmp_path / "src" / "utils.py").write_text("def bar():\n  pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_foo():\n  pass\n")
    (tmp_path / "lib.rs").write_text("fn main() {}\n")
    return tmp_path


def test_chunk_by_directory(sample_project: Path) -> None:
    sections = chunk_by_directory(str(sample_project))
    names = {s.name for s in sections}
    assert "src" in names
    assert "tests" in names
    src = next(s for s in sections if s.name == "src")
    assert src.file_count == 2


def test_chunk_by_complexity_all_low(sample_project: Path) -> None:
    sections = chunk_by_complexity(str(sample_project))
    assert len(sections) >= 1
    assert all(s.file_count >= 1 for s in sections)


def test_chunk_by_complexity_with_metrics(sample_project: Path) -> None:
    metrics = [
        {"file_path": "src/main.py", "sloc": 100, "avg_complexity": 20.0},
        {"file_path": "src/utils.py", "sloc": 50, "avg_complexity": 3.0},
        {"file_path": "tests/test_main.py", "sloc": 30, "avg_complexity": 1.0},
        {"file_path": "lib.rs", "sloc": 10, "avg_complexity": 1.0},
    ]
    sections = chunk_by_complexity(str(sample_project), file_metrics=metrics)
    names = {s.name for s in sections}
    assert "High complexity (hotspots)" in names
    assert "Low complexity" in names


def test_chunk_by_module_falls_back_to_directory(sample_project: Path) -> None:
    sections = chunk_by_module(str(sample_project))
    assert len(sections) >= 1


def test_chunk_by_module_with_edges(sample_project: Path) -> None:
    edges = [
        ("src/main.py", "src/utils.py"),
    ]
    sections = chunk_by_module(str(sample_project), import_edges=edges)
    assert any(s.file_count >= 2 for s in sections)


def test_analysis_section_to_dict(sample_project: Path) -> None:
    s = AnalysisSection(
        name="test", description="d", file_paths=["a.py"],
        file_count=1, total_sloc=100, avg_complexity=7.333,
    )
    d = s.to_dict()
    assert d["avg_complexity"] == 7.3
    assert d["file_count"] == 1
