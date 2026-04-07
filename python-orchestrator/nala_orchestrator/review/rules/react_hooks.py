from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import RawFinding
from .base import ReviewRule

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection


class StaleClosureRule(ReviewRule):
    name = "stale-closure"
    category = "react"
    severity = "high"
    languages = ["typescript", "tsx", "jsx", "javascript"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        lines = file_content.splitlines()

        for index, line in enumerate(lines, 1):
            if "useEffect(" not in line and "useCallback(" not in line:
                continue

            next_line = lines[index] if index < len(lines) else ""
            if "[]" not in line and "[]" not in next_line:
                continue

            findings.append(
                RawFinding(
                    rule_name=self.name,
                    category=self.category,
                    severity=self.severity,
                    file_path=file_path,
                    start_line=index,
                    end_line=min(index + 2, len(lines) or index),
                    description=(
                        "Potential stale closure. Hook has an empty dependency "
                        "array but might reference external variables."
                    ),
                    instruction=(
                        "Ensure all referenced variables from the component scope "
                        "are included in the dependency array, or use refs for "
                        "mutable values that should not trigger re-renders."
                    ),
                    identifiers=["useEffect", "useCallback"],
                )
            )

        return findings


class MissingCleanupRule(ReviewRule):
    name = "missing-cleanup"
    category = "react"
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
        if "addEventListener" not in file_content or "removeEventListener" in file_content:
            return findings

        for index, line in enumerate(file_content.splitlines(), 1):
            if "addEventListener" not in line:
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
                        "Event listener added without a corresponding cleanup "
                        "function (removeEventListener)."
                    ),
                    instruction=(
                        "Return a cleanup function from the useEffect hook that "
                        "calls removeEventListener."
                    ),
                    identifiers=["addEventListener"],
                )
            )

        return findings


react_rules = [StaleClosureRule(), MissingCleanupRule()]
