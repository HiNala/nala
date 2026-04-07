from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import RawFinding
from .base import ReviewRule

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection


class MissingLoadingGuardRule(ReviewRule):
    name = "missing-loading-guard"
    category = "concurrency"
    severity = "medium"
    languages = ["typescript", "tsx", "jsx", "javascript"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        if "async function handle" not in file_content and "async (e)" not in file_content:
            return findings

        for index, line in enumerate(file_content.splitlines(), 1):
            if not (
                re.search(r"async\s*(function)?\s*handle[A-Z]", line)
                or "=> async" in line
            ):
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
                        "Async handler might be missing a loading state guard, "
                        "allowing double-submissions."
                    ),
                    instruction=(
                        "Ensure the handler checks `if (isLoading) return;` at the "
                        "beginning and disables the button during execution."
                    ),
                    identifiers=[line.strip().split("(")[0]],
                )
            )
        return findings


concurrency_rules = [MissingLoadingGuardRule()]
