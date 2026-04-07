"""Unused code detection rules.

Detects imports that are declared but never referenced in the file body.
Works for Python, TypeScript, JavaScript, and Rust.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import RawFinding
from .base import ReviewRule

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection


def _parse_python_imports(content: str) -> list[tuple[str, int]]:
    """Return (identifier, 1-based line number) pairs for Python imports."""
    result: list[tuple[str, int]] = []
    for i, line in enumerate(content.splitlines(), 1):
        m = re.match(r"^\s*from\s+\S+\s+import\s+(.*)", line)
        if m:
            for raw in m.group(1).split(","):
                raw = raw.strip().strip("()")
                alias_m = re.match(r"\S+\s+as\s+(\S+)", raw)
                name = alias_m.group(1) if alias_m else raw.split()[0] if raw.split() else ""
                if name and name != "*":
                    result.append((name, i))
            continue
        m2 = re.match(r"^\s*import\s+(.*)", line)
        if m2:
            for part in m2.group(1).split(","):
                part = part.strip()
                alias_m = re.match(r"\S+\s+as\s+(\S+)", part)
                name = alias_m.group(1) if alias_m else part.split(".")[0]
                if name:
                    result.append((name, i))
    return result


def _parse_ts_imports(content: str) -> list[tuple[str, int]]:
    """Return (identifier, 1-based line number) for TS/JS named and default imports."""
    result: list[tuple[str, int]] = []
    for i, line in enumerate(content.splitlines(), 1):
        m = re.match(r'^\s*import\s+(?:type\s+)?\{([^}]+)\}', line)
        if m:
            for raw in m.group(1).split(","):
                raw = raw.strip()
                alias_m = re.match(r"\S+\s+as\s+(\S+)", raw)
                name = alias_m.group(1) if alias_m else raw.split()[0] if raw.split() else ""
                if name:
                    result.append((name, i))
            continue
        m2 = re.match(r'^\s*import\s+(\w+)\s+from', line)
        if m2:
            result.append((m2.group(1), i))
    return result


class UnusedPythonImportRule(ReviewRule):
    name = "unused-import"
    category = "unused"
    severity = "low"
    languages = ["python"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        lines = file_content.splitlines()
        for ident, line_no in _parse_python_imports(file_content):
            if not ident or len(ident) < 2:
                continue
            refs = [
                j for j, ln in enumerate(lines, 1)
                if j != line_no and re.search(r"\b" + re.escape(ident) + r"\b", ln)
            ]
            if not refs:
                findings.append(
                    RawFinding(
                        rule_name=self.name,
                        category=self.category,
                        severity=self.severity,
                        file_path=file_path,
                        start_line=line_no,
                        end_line=line_no,
                        description=f"`{ident}` is imported but never referenced in this file.",
                        instruction=f"Remove the unused import of `{ident}`.",
                        identifiers=[ident],
                    )
                )
        return findings


class UnusedTSImportRule(ReviewRule):
    name = "unused-import"
    category = "unused"
    severity = "low"
    languages = ["typescript", "tsx", "javascript", "jsx"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        lines = file_content.splitlines()
        for ident, line_no in _parse_ts_imports(file_content):
            if not ident or len(ident) < 2:
                continue
            refs = [
                j for j, ln in enumerate(lines, 1)
                if j != line_no and re.search(r"\b" + re.escape(ident) + r"\b", ln)
            ]
            if not refs:
                findings.append(
                    RawFinding(
                        rule_name=self.name,
                        category=self.category,
                        severity=self.severity,
                        file_path=file_path,
                        start_line=line_no,
                        end_line=line_no,
                        description=f"`{ident}` is imported but never used in this file.",
                        instruction=f"Remove `{ident}` from the import statement.",
                        identifiers=[ident],
                    )
                )
        return findings


class UnusedDestructuredRule(ReviewRule):
    """Detects destructured const/let variables never referenced after declaration."""

    name = "unused-destructured"
    category = "unused"
    severity = "low"
    languages = ["typescript", "tsx", "javascript", "jsx"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        lines = file_content.splitlines()
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*(?:const|let|var)\s+\{([^}]+)\}\s*=", line)
            if not m:
                continue
            for raw in m.group(1).split(","):
                raw = raw.strip()
                alias_m = re.match(r"\w+\s*:\s*(\w+)", raw)
                name = alias_m.group(1) if alias_m else raw.split()[0] if raw.split() else ""
                if not name or len(name) < 2 or name.startswith("_"):
                    continue
                refs = [
                    j for j, ln in enumerate(lines, 1)
                    if j != i and re.search(r"\b" + re.escape(name) + r"\b", ln)
                ]
                if not refs:
                    findings.append(
                        RawFinding(
                            rule_name=self.name,
                            category=self.category,
                            severity=self.severity,
                            file_path=file_path,
                            start_line=i,
                            end_line=i,
                            description=(
                                f"Destructured variable `{name}` is never referenced "
                                f"after line {i}."
                            ),
                            instruction=(
                                f"Remove `{name}` from the destructure or prefix with "
                                "`_` if intentionally unused."
                            ),
                            identifiers=[name],
                        )
                    )
        return findings


unused_rules = [UnusedPythonImportRule(), UnusedTSImportRule(), UnusedDestructuredRule()]
