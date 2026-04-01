"""
Session manager.

Every analysis run creates a session: a timestamped directory inside `.nala/sessions/`
containing the session metadata, findings, and generated reports.

Sessions are the audit trail. Nothing is lost. Everything is traceable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class SessionMeta:
    """Metadata stored in session.json."""

    session_id: str
    created_at: str
    project_root: str
    project_name: str
    total_files: int = 0
    total_symbols: int = 0
    perspectives_run: list[str] = field(default_factory=list)
    status: str = "in_progress"  # "in_progress" | "complete" | "error"


class SessionManager:
    """Creates and manages Nala analysis sessions."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.sessions_dir = project_root / ".nala" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._current: Optional[Path] = None
        self._meta: Optional[SessionMeta] = None

    # ── Create / open ──────────────────────────────────────────────────────

    def new_session(self) -> SessionMeta:
        """Create a new session directory and return its metadata."""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirs for organised output
        (session_dir / "reports").mkdir(exist_ok=True)
        (session_dir / "missions").mkdir(exist_ok=True)

        meta = SessionMeta(
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            project_root=str(self.project_root),
            project_name=self.project_root.name,
        )
        self._current = session_dir
        self._meta = meta
        self._save_meta()
        return meta

    def load_session(self, session_id: str) -> Optional[SessionMeta]:
        """Load an existing session by ID."""
        session_dir = self.sessions_dir / session_id
        meta_path = session_dir / "session.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        self._current = session_dir
        self._meta = SessionMeta(**data)
        return self._meta

    # ── Write ──────────────────────────────────────────────────────────────

    def write_file(self, filename: str, content: str) -> Path:
        """Write a file into the current session directory."""
        if not self._current:
            raise RuntimeError("No active session. Call new_session() first.")
        path = self._current / filename
        path.write_text(content, encoding="utf-8")
        return path

    def write_report(self, name: str, content: str) -> Path:
        """Write a markdown report into the session's reports/ subdirectory."""
        if not self._current:
            raise RuntimeError("No active session.")
        path = self._current / "reports" / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def write_mission(self, number: int, content: str) -> Path:
        """Write a mission document into the session's missions/ subdirectory."""
        if not self._current:
            raise RuntimeError("No active session.")
        path = self._current / "missions" / f"MISSION_{number:02d}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def update_meta(self, **kwargs) -> None:
        """Update metadata fields and persist to disk."""
        if not self._meta:
            return
        for key, val in kwargs.items():
            if hasattr(self._meta, key):
                setattr(self._meta, key, val)
        self._save_meta()

    def complete(self) -> None:
        """Mark the current session as complete."""
        self.update_meta(status="complete")

    # ── List ───────────────────────────────────────────────────────────────

    def list_sessions(self) -> list[SessionMeta]:
        """List all sessions, newest first."""
        sessions = []
        for d in sorted(self.sessions_dir.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            meta_path = d / "session.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text())
                    sessions.append(SessionMeta(**data))
                except Exception:
                    continue
        return sessions

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def current_dir(self) -> Optional[Path]:
        return self._current

    @property
    def current_meta(self) -> Optional[SessionMeta]:
        return self._meta

    # ── Private ────────────────────────────────────────────────────────────

    def _save_meta(self) -> None:
        if not self._current or not self._meta:
            return
        path = self._current / "session.json"
        path.write_text(
            json.dumps(asdict(self._meta), indent=2), encoding="utf-8"
        )
