"""
Complexity perspective.

Identifies functions with high cyclomatic complexity by querying the
indexed codebase. Does not require Neo4j — reads directly from the
SQLite cache built by the Rust indexer.

Thresholds (based on McCabe 1976 and NIST 500-235 guidelines):
  1–5:   Simple, low risk
  6–10:  Moderate, manageable
  11–20: Complex, high risk
  21+:   Very complex, untestable
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..sessions.report import Finding
from .base import BasePerspective, PerspectiveResult

if TYPE_CHECKING:
    pass

# Complexity thresholds
THRESHOLD_MEDIUM = 6
THRESHOLD_HIGH = 11
THRESHOLD_CRITICAL = 21


class ComplexityPerspective(BasePerspective):
    """Identifies overly complex functions by cyclomatic complexity score."""

    @property
    def name(self) -> str:
        return "complexity"

    @property
    def description(self) -> str:
        return "Flags functions with high cyclomatic complexity"

    async def analyze(self, project_root: str) -> PerspectiveResult:
        start = time.monotonic()
        findings: list[Finding] = []

        # Try graph-based analysis first (more detailed)
        if self.graph and self.graph.is_available():
            findings = await self._analyze_via_graph()
        else:
            findings = self._analyze_via_cache(project_root)

        duration_ms = int((time.monotonic() - start) * 1000)
        finding_count = len(findings)

        return PerspectiveResult(
            perspective_name=self.name,
            findings=findings,
            summary=(
                f"Found {finding_count} functions with complexity ≥ {THRESHOLD_MEDIUM}. "
                f"{sum(1 for f in findings if f.severity == 'critical')} critical, "
                f"{sum(1 for f in findings if f.severity == 'high')} high."
            ),
            duration_ms=duration_ms,
        )

    async def _analyze_via_graph(self) -> list[Finding]:
        """Query Neo4j for high-complexity functions."""
        from ..graph.queries import find_high_complexity_functions
        cypher, params = find_high_complexity_functions(threshold=THRESHOLD_MEDIUM)
        rows = self.graph.run(cypher, **params)

        findings = []
        for row in rows:
            cc = row.get("complexity", 0)
            severity = self._severity(cc)
            findings.append(Finding(
                title=f"High complexity: {row['name']} (CC={cc})",
                description=(
                    f"Function `{row['name']}` has a cyclomatic complexity of {cc}. "
                    f"High complexity increases the risk of bugs and makes the function "
                    f"harder to test and maintain. Consider breaking it into smaller functions."
                ),
                file_path=row.get("file_path", "unknown"),
                start_line=row.get("line", 0),
                severity=severity,
                perspective=self.name,
                suggestion=self._suggestion(cc),
            ))
        return findings

    def _analyze_via_cache(self, project_root: str) -> list[Finding]:
        """
        Analyse complexity by reading the SQLite cache.

        Uses a simple heuristic: count decision-point keywords per function
        from the cached source. Full metric integration in Mission 09.
        """
        findings: list[Finding] = []
        root = Path(project_root)
        db_path = root / ".nala" / "cache.db"

        if not db_path.exists():
            return findings

        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT relative_path, language FROM file_index WHERE language IS NOT NULL"
            )
            rows = cursor.fetchall()
            conn.close()

            for rel_path, language in rows:
                abs_path = root / rel_path
                if abs_path.exists():
                    findings.extend(
                        self._scan_file_complexity(abs_path, rel_path, language or "")
                    )
        except Exception as e:
            return [Finding(
                title="Complexity analysis error",
                description=str(e),
                file_path="",
                start_line=0,
                severity="low",
                perspective=self.name,
            )]

        return findings

    def _scan_file_complexity(
        self, path: Path, rel_path: str, language: str
    ) -> list[Finding]:
        """Very simple per-function complexity scan based on line heuristics."""
        findings = []
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        # Naive approach: count decision keywords per 'block' separated by function lines
        # Real implementation in Mission 03 uses Tree-sitter + rust-code-analysis
        keywords = {"if ", "elif ", "else if ", "while ", "for ", "match ", "case ", "&&", "||"}
        lines = source.splitlines()
        cc = 1  # Base complexity
        for line in lines:
            stripped = line.strip()
            for kw in keywords:
                if kw in stripped:
                    cc += 1

        if cc >= THRESHOLD_HIGH:
            severity = self._severity(cc)
            findings.append(Finding(
                title=f"High file complexity: {rel_path} (CC≈{cc})",
                description=(
                    f"`{rel_path}` has an estimated cyclomatic complexity of {cc}. "
                    "Consider decomposing large functions and reducing branching."
                ),
                file_path=rel_path,
                start_line=1,
                severity=severity,
                perspective=self.name,
                suggestion=self._suggestion(cc),
            ))

        return findings

    @staticmethod
    def _severity(cc: int) -> str:
        if cc >= THRESHOLD_CRITICAL:
            return "critical"
        if cc >= THRESHOLD_HIGH:
            return "high"
        if cc >= THRESHOLD_MEDIUM:
            return "medium"
        return "low"

    @staticmethod
    def _suggestion(cc: int) -> str:
        if cc >= THRESHOLD_CRITICAL:
            return (
                "This function is extremely complex and nearly untestable. "
                "Break it into 5+ smaller functions, each with a single responsibility."
            )
        if cc >= THRESHOLD_HIGH:
            return (
                "Extract 2-3 smaller functions from this one. "
                "Each extracted function should have cyclomatic complexity ≤ 5."
            )
        return "Consider simplifying conditional logic or extracting helper functions."
