"""
Test coverage perspective.

Identifies source files with no corresponding test file using structural
heuristics. Does not require running tests or parsing coverage reports —
just file naming conventions.

Convention matching:
  src/auth.py           → tests/test_auth.py  or  tests/auth_test.py
  src/auth/service.py   → tests/auth/test_service.py
  src/lib.rs            → src/tests.rs  or  tests/
  src/utils.ts          → src/utils.test.ts  or  src/__tests__/utils.test.ts
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from .base import BasePerspective, PerspectiveResult
from ..sessions.report import Finding

if TYPE_CHECKING:
    pass

# Source extensions and their expected test patterns
_SOURCE_EXTS = {".py", ".rs", ".js", ".ts", ".jsx", ".tsx"}
_SKIP_DIRS   = {
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".nala", "migrations",
}
_TEST_INDICATORS = {
    "test", "tests", "spec", "specs", "__tests__", "testing",
}


class TestCoveragePerspective(BasePerspective):
    """Flags source files with no matching test file."""

    @property
    def name(self) -> str:
        return "test_coverage"

    @property
    def description(self) -> str:
        return "Identifies source files with no corresponding test coverage"

    async def analyze(self, project_root: str) -> PerspectiveResult:
        start = time.monotonic()
        root = Path(project_root)

        # Gather all files
        all_files = list(_iter_non_skipped(root))

        # Partition into source and test files
        test_files = {f for f in all_files if _is_test_file(f, root)}
        source_files = [
            f for f in all_files
            if f.suffix in _SOURCE_EXTS and not _is_test_file(f, root)
        ]

        # Build a set of test paths for fast lookup
        test_stems = _build_test_stems(test_files, root)

        # Find untested source files
        findings: list[Finding] = []
        untested = 0
        for src in source_files:
            if not _has_test(src, root, test_stems):
                untested += 1
                rel = str(src.relative_to(root))
                findings.append(Finding(
                    title=f"No test file found: {rel}",
                    description=(
                        f"`{rel}` has no corresponding test file. "
                        "Untested code is risky to refactor and may contain undetected bugs."
                    ),
                    file_path=rel,
                    start_line=1,
                    severity=_severity(src),
                    perspective=self.name,
                    suggestion=_suggest_test_path(src, root),
                ))

        total = len(source_files)
        tested = total - untested
        ratio = (tested / total * 100) if total > 0 else 100.0

        # Sort: most important (larger files) first
        findings.sort(key=lambda f: f.file_path)

        duration_ms = int((time.monotonic() - start) * 1000)
        return PerspectiveResult(
            perspective_name=self.name,
            findings=findings,
            summary=(
                f"Test coverage: {tested}/{total} source files have tests "
                f"({ratio:.0f}%). {untested} files have no test file."
            ),
            duration_ms=duration_ms,
        )


# ── Helpers ────────────────────────────────────────────────────────────────

def _iter_non_skipped(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(p in _SKIP_DIRS for p in path.parts):
            continue
        yield path


def _is_test_file(path: Path, root: Path) -> bool:
    """Return True if this file is a test file by name or location."""
    stem = path.stem.lower()
    parts_lower = {p.lower() for p in path.parts}
    # Directory-based: lives in tests/, spec/, __tests__/
    if parts_lower & _TEST_INDICATORS:
        return True
    # Name-based: test_foo.py, foo_test.py, foo.test.ts, foo.spec.ts
    if stem.startswith("test_") or stem.endswith("_test"):
        return True
    if ".test." in path.name or ".spec." in path.name:
        return True
    return False


def _build_test_stems(test_files, root: Path) -> set[str]:
    """Build a set of normalised stems from all test files."""
    stems = set()
    for f in test_files:
        stem = f.stem.lower()
        # Remove test_ prefix and _test / .test / .spec suffixes
        stem = stem.removeprefix("test_")
        stem = stem.removesuffix("_test")
        for suffix in (".test", ".spec"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        stems.add(stem)
    return stems


def _has_test(src: Path, root: Path, test_stems: set[str]) -> bool:
    """Return True if a source file appears to have a test."""
    stem = src.stem.lower()
    return stem in test_stems


def _severity(src: Path) -> str:
    """Severity based on file extension — all untested code is medium."""
    # Could be upgraded to high for complex files in a future iteration
    return "medium"


def _suggest_test_path(src: Path, root: Path) -> str:
    """Suggest where to put the test file for this source file."""
    rel = src.relative_to(root)
    ext = src.suffix
    stem = src.stem

    if ext == ".py":
        return f"Create `tests/test_{stem}.py` or `tests/{rel.parent}/test_{stem}.py`"
    if ext == ".rs":
        return f"Add a `#[cfg(test)]` module at the bottom of `{rel}` or create `tests/{stem}.rs`"
    if ext in (".js", ".jsx"):
        return f"Create `{rel.parent}/{stem}.test.js` or `{rel.parent}/__tests__/{stem}.test.js`"
    if ext in (".ts", ".tsx"):
        return f"Create `{rel.parent}/{stem}.test.ts` or `{rel.parent}/__tests__/{stem}.test.ts`"
    return f"Create a test file for `{rel}`"
