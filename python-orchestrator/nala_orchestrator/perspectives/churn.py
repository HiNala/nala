"""
Code churn perspective.

Uses git history to identify files that change frequently. High churn often
signals unstable hotspots that should be refactored or covered by tests.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from ..sessions.report import Finding
from .base import BasePerspective, PerspectiveResult


class ChurnPerspective(BasePerspective):
    @property
    def name(self) -> str:
        return "churn"

    @property
    def description(self) -> str:
        return "Finds frequently modified files from git history"

    async def analyze(self, project_root: str) -> PerspectiveResult:
        start = time.monotonic()
        findings: list[Finding] = []
        root = Path(project_root)

        if not (root / ".git").exists():
            return PerspectiveResult(
                perspective_name=self.name,
                summary="Git repository not found; churn analysis skipped.",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            proc = subprocess.run(
                ["git", "log", "--name-only", "--pretty=format:"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            counts: dict[str, int] = {}
            for line in proc.stdout.splitlines():
                path = line.strip()
                if not path:
                    continue
                counts[path] = counts.get(path, 0) + 1

            for file_path, changes in sorted(counts.items(), key=lambda item: -item[1])[:25]:
                if changes < 10:
                    continue
                severity = "high" if changes >= 30 else "medium"
                findings.append(
                    Finding(
                        title=f"High churn file: {file_path} ({changes} commits)",
                        description=(
                            f"`{file_path}` changed in {changes} commits. "
                            "Frequent edits increase regression risk and suggest "
                            "design instability."
                        ),
                        file_path=file_path,
                        start_line=1,
                        severity=severity,
                        perspective=self.name,
                        suggestion="Stabilize APIs, add focused tests, and split responsibilities.",
                    )
                )
        except Exception as exc:
            findings.append(
                Finding(
                    title="Churn analysis error",
                    description=str(exc),
                    file_path="",
                    start_line=0,
                    severity="low",
                    perspective=self.name,
                )
            )

        return PerspectiveResult(
            perspective_name=self.name,
            findings=findings,
            summary=f"Churn analysis found {len(findings)} high-change file(s).",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
