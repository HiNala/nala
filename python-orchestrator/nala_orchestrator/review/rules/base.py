from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..models import RawFinding

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection


class ReviewRule(ABC):
    name: str
    category: str
    severity: str  # "critical" | "high" | "medium" | "low" | "info"
    languages: list[str]  # e.g. ["python"], ["typescript", "tsx", "javascript"]

    @abstractmethod
    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        """Check a single file's content and graph context to return raw findings."""
