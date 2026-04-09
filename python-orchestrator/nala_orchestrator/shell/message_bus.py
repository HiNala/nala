"""Mission 31: Shell message bus — cross-process IPC for the interpreter shell.

Architecture: append-only JSONL file in .nala/bus/messages.jsonl.
Agents (subprocess or asyncio) write messages; the TUI bridge tails the file
and forwards new lines to the Rust TUI via the existing IPC channel.

This works across OS processes without networking. On Windows the file-polling
fallback is used (inotify is Linux-only).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import AsyncIterator

log = logging.getLogger(__name__)

# ── Message types ──────────────────────────────────────────────────────────

MSG_TEXT = "text"
MSG_STATUS = "status"
MSG_APPROVAL = "approval_request"
MSG_APPROVAL_RESPONSE = "approval_response"
MSG_ERROR = "error"
MSG_PROGRESS = "progress"
MSG_CODE_DIFF = "code_diff"


@dataclass
class ShellMessage:
    source: str               # "nala" | "you" | agent_id
    content: str
    message_type: str = MSG_TEXT
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    requires_response: bool = False
    response_options: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, line: str) -> ShellMessage:
        data = json.loads(line)
        return cls(**data)

    def format_display(self) -> str:
        """Human-readable one-liner for the TUI feed."""
        label = f"[{self.source:<12}]"
        return f"  {label}  {self.content}"


# ── Bus ────────────────────────────────────────────────────────────────────

class ShellMessageBus:
    """File-backed cross-process message bus.

    Writers call :meth:`post` (thread-safe, no async needed).
    Readers call :meth:`subscribe` to get an async iterator of new messages.
    """

    def __init__(self, nala_dir: Path) -> None:
        self._bus_dir = nala_dir / "bus"
        self._bus_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._bus_dir / "messages.jsonl"
        self._response_file = self._bus_dir / "responses.jsonl"
        self._pending_approvals: dict[str, ShellMessage] = {}
        self._response_callbacks: dict[str, asyncio.Future] = {}  # type: ignore[type-arg]

    # ── Write ──────────────────────────────────────────────────────────────

    def post(self, message: ShellMessage) -> None:
        """Append a message to the bus (safe from any thread/process)."""
        try:
            with self._log_file.open("a", encoding="utf-8") as fh:
                fh.write(message.to_json() + "\n")
        except OSError as e:
            log.warning("Bus write failed: %s", e)
        if message.requires_response:
            self._pending_approvals[message.message_id] = message

    def post_text(self, source: str, content: str) -> None:
        self.post(ShellMessage(source=source, content=content))

    def post_status(self, source: str, content: str) -> None:
        self.post(ShellMessage(source=source, content=content, message_type=MSG_STATUS))

    def post_error(self, source: str, content: str) -> None:
        self.post(ShellMessage(source=source, content=content, message_type=MSG_ERROR))

    def post_approval(
        self,
        source: str,
        content: str,
        options: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Post an approval request and return its message_id."""
        msg = ShellMessage(
            source=source,
            content=content,
            message_type=MSG_APPROVAL,
            requires_response=True,
            response_options=options or ["y", "n"],
            metadata=metadata or {},
        )
        self.post(msg)
        return msg.message_id

    # ── Read ───────────────────────────────────────────────────────────────

    def get_pending_approvals(self) -> list[ShellMessage]:
        return list(self._pending_approvals.values())

    def respond(self, message_id: str, response: str) -> None:
        """Record a user response; removes the pending approval entry."""
        self._pending_approvals.pop(message_id, None)
        resp_msg = ShellMessage(
            source="you",
            content=response,
            message_type=MSG_APPROVAL_RESPONSE,
            metadata={"responding_to": message_id},
        )
        try:
            with self._response_file.open("a", encoding="utf-8") as fh:
                fh.write(resp_msg.to_json() + "\n")
        except OSError as e:
            log.warning("Response write failed: %s", e)
        # Wake any waiting coroutine
        fut = self._response_callbacks.pop(message_id, None)
        if fut and not fut.done():
            fut.set_result(response)

    async def wait_for_response(self, message_id: str, timeout: float = 300) -> str | None:
        """Await the user's response to an approval request."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[str] = loop.create_future()
        self._response_callbacks[message_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._response_callbacks.pop(message_id, None)
            return None

    async def subscribe(self, poll_interval: float = 0.2) -> AsyncIterator[ShellMessage]:
        """Yield new messages as they arrive (file-poll based)."""
        position = self._log_file.stat().st_size if self._log_file.exists() else 0
        while True:
            await asyncio.sleep(poll_interval)
            if not self._log_file.exists():
                continue
            try:
                with self._log_file.open("r", encoding="utf-8") as fh:
                    fh.seek(position)
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                yield ShellMessage.from_json(line)
                            except Exception as e:
                                log.debug("Malformed bus line: %s", e)
                    position = fh.tell()
            except OSError:
                pass

    def replay(self, limit: int = 200) -> list[ShellMessage]:
        """Return the last N messages for session restore."""
        if not self._log_file.exists():
            return []
        try:
            lines = self._log_file.read_text(encoding="utf-8").splitlines()
            messages: list[ShellMessage] = []
            for line in lines[-limit:]:
                line = line.strip()
                if line:
                    try:
                        messages.append(ShellMessage.from_json(line))
                    except Exception:
                        pass
            return messages
        except OSError:
            return []
