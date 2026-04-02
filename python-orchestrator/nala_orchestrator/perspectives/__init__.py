"""Analysis perspectives — each is a distinct analytical lens on the codebase."""

from .base import BasePerspective, PerspectiveResult
from .churn import ChurnPerspective
from .complexity import ComplexityPerspective
from .dead_code import DeadCodePerspective
from .dependency import DependencyPerspective
from .duplication import DuplicationPerspective
from .engine import PerspectivesEngine, format_results_as_text
from .performance import PerformancePerspective
from .security import SecurityPerspective
from .test_coverage import TestCoveragePerspective

__all__ = [
    "BasePerspective",
    "PerspectiveResult",
    "ComplexityPerspective",
    "ChurnPerspective",
    "DeadCodePerspective",
    "DependencyPerspective",
    "DuplicationPerspective",
    "PerformancePerspective",
    "PerspectivesEngine",
    "SecurityPerspective",
    "TestCoveragePerspective",
    "format_results_as_text",
]
