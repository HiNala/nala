from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import RawFinding
from .base import ReviewRule

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection


class SilentFallbackRule(ReviewRule):
    name = "silent-fallback"
    category = "error_handling"
    severity = "medium"
    languages = ["typescript", "tsx", "jsx", "javascript", "python", "rust"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        for index, line in enumerate(file_content.splitlines(), 1):
            if "?? \"\"" not in line and "?? null" not in line:
                continue
            findings.append(
                RawFinding(
                    rule_name=self.name,
                    category=self.category,
                    severity=self.severity,
                    file_path=file_path,
                    start_line=index,
                    end_line=index,
                    description=(
                        "Silent fallback used which may mask parsing errors or "
                        "missing API responses."
                    ),
                    instruction=(
                        "Remove the silent fallback and instead add proper error "
                        "handling, logging, or throw an explicit error to fail fast."
                    ),
                    identifiers=["??"],
                )
            )
        return findings


class EmptyCatchRule(ReviewRule):
    name = "empty-catch"
    category = "error_handling"
    severity = "high"
    languages = ["typescript", "tsx", "jsx", "javascript", "python"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        if not (
            re.search(r"catch\s*\([^\)]*\)\s*\{\s*\}", file_content)
            or re.search(r"except[^:]*:\s*pass", file_content)
        ):
            return findings

        for index, line in enumerate(file_content.splitlines(), 1):
            if "catch" not in line or "}" not in line or "{" not in line:
                continue
            findings.append(
                RawFinding(
                    rule_name=self.name,
                    category=self.category,
                    severity=self.severity,
                    file_path=file_path,
                    start_line=index,
                    end_line=index,
                    description=(
                        "Empty catch block found. Errors are being swallowed silently."
                    ),
                    instruction=(
                        "Add meaningful error handling or logging inside the catch "
                        "block to track exceptions."
                    ),
                    identifiers=["catch"],
                )
            )
        return findings


error_rules = [SilentFallbackRule(), EmptyCatchRule()]
