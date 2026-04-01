"""Agent message bus.

Provides targeted and broadcast messaging between agents.
Messages are queued in memory and consumed by the recipient at the
start of its next turn.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


@dataclass
class AgentMessage:
    """A message sent from one agent to another."""
    from_agent: str
    to_agent: str          # empty string = broadcast
    content: str
    timestamp: float = field(default_factory=time.time)
    read: bool = False

    def format(self) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        src = self.from_agent or "system"
        return f"[{ts}] Message from {src}: {self.content}"


class MessageBus:
    """In-memory message queue for inter-agent communication."""

    def __init__(self) -> None:
        self._queues: dict[str, list[AgentMessage]] = defaultdict(list)
        self._broadcast_log: list[AgentMessage] = []
        self._mutex = Lock()

    def send(self, from_agent: str, to_agent: str, content: str) -> None:
        """Send a targeted message."""
        msg = AgentMessage(from_agent=from_agent, to_agent=to_agent, content=content)
        with self._mutex:
            self._queues[to_agent].append(msg)

    def broadcast(self, from_agent: str, content: str) -> None:
        """Send a message to all agents."""
        msg = AgentMessage(from_agent=from_agent, to_agent="", content=content)
        with self._mutex:
            self._broadcast_log.append(msg)

    def get_messages(self, agent_id: str, since: Optional[float] = None) -> list[AgentMessage]:
        """Get unread messages for an agent (targeted + broadcasts)."""
        with self._mutex:
            # Targeted messages
            targeted = [m for m in self._queues[agent_id] if not m.read]
            # Broadcasts not yet seen by this agent
            broadcasts = [
                m for m in self._broadcast_log
                if not m.read
                and (since is None or m.timestamp > since)
                and m.from_agent != agent_id
            ]
            msgs = sorted(targeted + broadcasts, key=lambda m: m.timestamp)
            for m in msgs:
                m.read = True
            return msgs

    def has_messages(self, agent_id: str) -> bool:
        with self._mutex:
            return bool([m for m in self._queues[agent_id] if not m.read])

    def format_for_agent(self, agent_id: str) -> str:
        """Return a formatted string of pending messages for context injection."""
        msgs = self.get_messages(agent_id)
        if not msgs:
            return ""
        lines = ["[INCOMING MESSAGES]"]
        for m in msgs:
            lines.append(m.format())
        lines.append("[END MESSAGES]")
        return "\n".join(lines)

    def clear(self) -> None:
        with self._mutex:
            self._queues.clear()
            self._broadcast_log.clear()
