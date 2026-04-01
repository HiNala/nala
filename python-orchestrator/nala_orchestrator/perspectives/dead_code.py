"""Dead code perspective — stub for Mission 09."""
from .base import BasePerspective, PerspectiveResult


class DeadCodePerspective(BasePerspective):
    """Finds functions defined but never called."""

    @property
    def name(self) -> str:
        return "dead_code"

    @property
    def description(self) -> str:
        return "Finds functions and classes that are defined but never referenced"

    def requires_graph(self) -> bool:
        return True

    async def analyze(self, project_root: str) -> PerspectiveResult:
        # TODO (Mission 09): implement dead code detection via call graph
        return PerspectiveResult(
            perspective_name=self.name,
            summary="Dead code perspective — full implementation in Mission 09.",
        )
