"""
Inline agent actions — stub for Mission 13.

These are operations the agent can perform directly on files:
refactor a function, fix a bug, apply a suggestion from the audit report.

All actions require explicit user confirmation before modifying files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nala_orchestrator.config import Config


class AgentActions:
    """Performs inline code modifications with explicit user confirmation."""

    def __init__(self, config: "Config") -> None:
        self.config = config

    async def refactor_function(
        self, file_path: str, function_name: str, instruction: str
    ) -> str:
        """
        Refactor a specific function based on an instruction.

        TODO (Mission 13): implement file read → LLM transform → diff preview → confirm → write.
        """
        return (
            f"Inline actions not yet implemented. "
            f"Planned for Mission 13: would refactor `{function_name}` in `{file_path}`."
        )

    async def apply_suggestion(self, file_path: str, line: int, suggestion: str) -> str:
        """
        Apply a suggestion from the audit report at a specific file/line.

        TODO (Mission 13): implement suggestion application with diff preview.
        """
        return f"Inline actions not yet implemented (Mission 13)."
