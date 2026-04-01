"""Analysis perspectives — each is a distinct analytical lens on the codebase."""
from .base import BasePerspective, PerspectiveResult
from .complexity import ComplexityPerspective

__all__ = ["BasePerspective", "PerspectiveResult", "ComplexityPerspective"]
