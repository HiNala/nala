"""
Base perspective class.

All analysis perspectives extend BasePerspective. Each perspective is a
specific analytical lens applied to the codebase graph: complexity, dependency,
coverage, churn, dead code, performance.

To add a new perspective:
  1. Create a new file (e.g. my_perspective.py)
  2. Extend BasePerspective
  3. Implement analyze() and description
  4. Add it to perspectives/__init__.py and the perspective registry
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nala_orchestrator.config import Config
    from nala_orchestrator.graph.connection import GraphConnection
    from nala_orchestrator.sessions.report import Finding


@dataclass
class PerspectiveResult:
    """The output of running one perspective."""

    perspective_name: str
    findings: list["Finding"] = field(default_factory=list)
    summary: str = ""
    duration_ms: int = 0
    error: Optional[str] = None

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")


class BasePerspective(ABC):
    """Abstract base for all analysis perspectives."""

    def __init__(self, config: "Config", graph: Optional["GraphConnection"] = None) -> None:
        self.config = config
        self.graph = graph

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this perspective (e.g. 'complexity')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description shown in the TUI and reports."""
        ...

    @abstractmethod
    async def analyze(self, project_root: str) -> PerspectiveResult:
        """Run the analysis and return findings."""
        ...

    def requires_graph(self) -> bool:
        """Return True if this perspective needs a live Neo4j connection."""
        return False
