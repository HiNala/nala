from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import RawFinding
from .base import ReviewRule

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection


class StaleTodoRule(ReviewRule):
    name = "stale-todo"
    category = "consistency"
    severity = "info"
    languages = ["python", "typescript", "rust", "javascript"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        for index, line in enumerate(file_content.splitlines(), 1):
            if not re.search(r"(?i)(TODO|FIXME)\s*:", line):
                continue
            findings.append(
                RawFinding(
                    rule_name=self.name,
                    category=self.category,
                    severity=self.severity,
                    file_path=file_path,
                    start_line=index,
                    end_line=index,
                    description="TODO or FIXME comment found. Ensure it is still relevant.",
                    instruction=(
                        "Resolve the TODO or link it to an active issue tracking ticket."
                    ),
                    identifiers=["TODO", "FIXME"],
                )
            )
        return findings


consistency_rules = [StaleTodoRule()]
