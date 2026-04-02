"""
Performance perspective.

Lightweight static heuristics for common performance anti-patterns in source
files. Intended as a quick signal, not a profiler replacement.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from ..sessions.report import Finding
from .base import BasePerspective, PerspectiveResult

_SKIP_DIRS = {
    "node_modules",
    "target",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".nala",
}

_SOURCE_EXTS = {".py", ".rs", ".js", ".ts", ".jsx", ".tsx"}


class PerformancePerspective(BasePerspective):
    @property
    def name(self) -> str:
        return "performance"

    @property
    def description(self) -> str:
        return "Flags basic static performance anti-patterns"

    async def analyze(self, project_root: str) -> PerspectiveResult:
        start = time.monotonic()
        root = Path(project_root)
        findings: list[Finding] = []

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if path.suffix not in _SOURCE_EXTS:
                continue

            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            rel = str(path.relative_to(root))
            lines = source.splitlines()
            for i, line in enumerate(lines, start=1):
                stripped = line.strip()
                if _looks_like_nested_loop(stripped):
                    findings.append(
                        Finding(
                            title="Potential nested loop hotspot",
                            description=(
                                "Nested loops can become expensive on large datasets "
                                "(often O(n^2) or worse)."
                            ),
                            file_path=rel,
                            start_line=i,
                            severity="medium",
                            perspective=self.name,
                            suggestion=(
                                "Consider indexing, pre-grouping, or reducing "
                                "inner-loop work."
                            ),
                            code_snippet=stripped[:200],
                        )
                    )
                if ".collect::<Vec<_>>()" in stripped and ".iter()" in stripped:
                    findings.append(
                        Finding(
                            title="Potential unnecessary allocation",
                            description=(
                                "Collecting intermediate vectors in hot paths can "
                                "increase allocations."
                            ),
                            file_path=rel,
                            start_line=i,
                            severity="low",
                            perspective=self.name,
                            suggestion="Try iterators/lazy pipelines or pre-allocated buffers.",
                            code_snippet=stripped[:200],
                        )
                    )

        return PerspectiveResult(
            perspective_name=self.name,
            findings=findings[:100],
            summary=f"Performance scan found {len(findings[:100])} potential hotspot(s).",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _looks_like_nested_loop(line: str) -> bool:
    if re.search(r"\bfor\b.*\bfor\b", line):
        return True
    if re.search(r"\bwhile\b.*\bwhile\b", line):
        return True
    return False
