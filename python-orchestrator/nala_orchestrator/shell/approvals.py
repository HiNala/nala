"""Mission 31: Approval flow — gated change requests from agents to the user.

When an agent wants to modify files it must post an approval request through
the bus. The interpreter shell renders it; the user responds with y/n/view/edit.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .message_bus import ShellMessageBus

log = logging.getLogger(__name__)


@dataclass
class ApprovalRequest:
    agent_id: str
    description: str
    diff_preview: str        # Short diff summary shown inline
    full_diff: str           # Full diff shown on 'v' / 'view'
    files_affected: list[str]
    message_id: str = ""     # Set after posting to bus


@dataclass
class ApprovalResult:
    approved: bool
    response: str            # raw user response: "y", "n", "v", "e"
    edited: bool = False


class ApprovalGate:
    """Manages in-flight approval requests for one orchestration session."""

    def __init__(self, bus: ShellMessageBus) -> None:
        self._bus = bus
        self._pending: dict[str, ApprovalRequest] = {}

    async def request(
        self,
        req: ApprovalRequest,
        timeout: float = 300,
    ) -> ApprovalResult:
        """Post an approval request and wait for the user's response.

        Returns immediately if the user responds; times out after *timeout* seconds
        and returns a rejection so the agent can continue without hanging forever.
        """
        content = _format_request(req)
        msg_id = self._bus.post_approval(
            source=req.agent_id,
            content=content,
            options=["y", "n", "v", "e"],
            metadata={
                "files": req.files_affected,
                "diff_preview": req.diff_preview,
            },
        )
        req.message_id = msg_id
        self._pending[msg_id] = req

        try:
            response = await self._bus.wait_for_response(msg_id, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

        if response is None:
            log.warning("Approval timeout for %s — auto-rejecting", msg_id)
            return ApprovalResult(approved=False, response="timeout")

        resp = (response or "n").lower().strip()
        return ApprovalResult(
            approved=resp in {"y", "yes"},
            response=resp,
        )

    def get_pending(self) -> list[ApprovalRequest]:
        return list(self._pending.values())


def _format_request(req: ApprovalRequest) -> str:
    files = ", ".join(req.files_affected[:3])
    if len(req.files_affected) > 3:
        files += f" (+{len(req.files_affected) - 3} more)"
    lines = [
        f"Proposed changes to {files}:",
        "",
        req.diff_preview,
        "",
        "[y] Apply  [n] Reject  [v] View full diff  [e] Edit first",
    ]
    return "\n".join(lines)
