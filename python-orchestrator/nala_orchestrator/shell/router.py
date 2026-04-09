"""Mission 31: Input router — directs user input to the right agent/system.

Routing priority:
  1. Pending approval response  → the agent waiting for y/n
  2. @mention routing           → a specific named agent
  3. /command                   → system command handler
  4. Everything else            → main Nala agent (LLM query)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .message_bus import ShellMessageBus


# ── Route types ────────────────────────────────────────────────────────────

@dataclass
class RouteToApproval:
    message_id: str
    response: str


@dataclass
class RouteToAgent:
    agent_id: str
    message: str


@dataclass
class RouteToSystem:
    command: str


@dataclass
class RouteToMainAgent:
    message: str


RoutingDecision = RouteToApproval | RouteToAgent | RouteToSystem | RouteToMainAgent

_MENTION_RE = re.compile(r"^@([\w\-]+)\s*(.*)", re.DOTALL)
_STOP_CMDS = {"/stop", "/cancel", "/kill"}


@dataclass
class ShellContext:
    """Snapshot of relevant state used by the router."""
    pending_approval_id: str | None = None
    active_agent_ids: list[str] | None = None

    def has_pending_approval(self) -> bool:
        return self.pending_approval_id is not None


class InputRouter:
    """Stateless router — call :meth:`route` on every user keystroke submit."""

    def route(self, user_input: str, context: ShellContext) -> RoutingDecision:
        stripped = user_input.strip()
        if not stripped:
            return RouteToMainAgent(message="")

        # 1. Pending approval
        if context.has_pending_approval():
            resp = stripped.lower()
            if resp in {"y", "yes", "n", "no", "v", "view", "e", "edit"} or resp.isdigit():
                return RouteToApproval(
                    message_id=context.pending_approval_id,  # type: ignore[arg-type]
                    response=resp,
                )

        # 2. @mention
        m = _MENTION_RE.match(stripped)
        if m:
            agent_id = m.group(1)
            msg = m.group(2).strip()
            return RouteToAgent(agent_id=agent_id, message=msg)

        # 3. /command
        if stripped.startswith("/"):
            return RouteToSystem(command=stripped)

        # 4. Free text → main agent
        return RouteToMainAgent(message=stripped)

    def is_stop_command(self, user_input: str) -> bool:
        return user_input.strip().lower().split()[0] in _STOP_CMDS if user_input.strip() else False
