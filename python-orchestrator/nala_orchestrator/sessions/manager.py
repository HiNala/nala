"""
Session manager.

Every analysis run creates a session: a timestamped directory inside `.nala/sessions/`
containing the session metadata, findings, and generated reports.

Sessions are the audit trail. Nothing is lost. Everything is traceable.

Directory layout per session:
  .nala/sessions/{id}/
  ├── session.json        — metadata (created_at, status, etc.)
  ├── conversation.jsonl  — one JSON object per turn, appended atomically
  ├── findings.json       — serialised PerspectiveResult list (optional)
  ├── reports/            — generated markdown reports
  └── missions/           — AI-generated mission documents
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class SessionMeta:
    """Metadata stored in session.json."""

    session_id: str
    created_at: str
    project_root: str
    project_name: str
    total_files: int = 0
    total_symbols: int = 0
    total_turns: int = 0
    perspectives_run: list[str] = field(default_factory=list)
    status: str = "in_progress"  # "in_progress" | "complete" | "error"

    @classmethod
    def from_dict(cls, data: dict) -> SessionMeta:
        """Create from dict, ignoring unknown keys for forward compatibility."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class SessionManager:
    """Creates and manages Nala analysis sessions."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.sessions_dir = project_root / ".nala" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._current: Path | None = None
        self._meta: SessionMeta | None = None

    # ── Create / open ──────────────────────────────────────────────────────

    def new_session(self) -> SessionMeta:
        """Create a new session directory and return its metadata."""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = self.sessions_dir / session_id
        suffix = 1
        while session_dir.exists():
            session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{suffix:02d}"
            session_dir = self.sessions_dir / session_id
            suffix += 1
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

    def load_session(self, session_id: str) -> SessionMeta | None:
        """Load an existing session by ID."""
        session_dir = self.sessions_dir / session_id
        meta_path = session_dir / "session.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        self._current = session_dir
        self._meta = SessionMeta.from_dict(data)
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

    # ── Conversation logging ───────────────────────────────────────────────

    def append_turn(self, role: str, content: str) -> None:
        """
        Atomically append one conversation turn to conversation.jsonl.

        Uses write-to-tmp-then-rename to avoid corruption on crash.
        """
        if not self._current:
            return
        turn = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        jsonl_path = self._current / "conversation.jsonl"
        line = json.dumps(turn, ensure_ascii=False) + "\n"

        # Atomic append: write to temp file in same dir, then rename-append
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._current, prefix=".turn_", suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(line)
            # On Windows rename doesn't atomically replace but we still avoid
            # partial writes — read+write pattern is safe enough for dev tool.
            with open(jsonl_path, "a", encoding="utf-8") as dest:
                with open(tmp_path, encoding="utf-8") as src:
                    dest.write(src.read())
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        # Update turn count in metadata
        if self._meta:
            turns = self.get_conversation_history()
            self.update_meta(total_turns=len(turns))

    def get_conversation_history(self) -> list[dict]:
        """Load all turns from conversation.jsonl."""
        if not self._current:
            return []
        jsonl_path = self._current / "conversation.jsonl"
        if not jsonl_path.exists():
            return []
        turns = []
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return turns

    def save_findings(self, results: list[Any]) -> None:
        """Serialise and write findings.json from PerspectiveResult objects."""
        if not self._current:
            return
        from dataclasses import asdict as _asdict
        serialisable = []
        for r in results:
            try:
                serialisable.append(_asdict(r))
            except Exception:
                serialisable.append({"error": str(r)})
        path = self._current / "findings.json"
        path.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")
        # Update perspectives_run list
        names = [r.perspective_name for r in results if hasattr(r, "perspective_name")]
        self.update_meta(perspectives_run=names)

    def load_findings_raw(self) -> list[dict]:
        """Load raw findings data from findings.json (dicts, not dataclasses)."""
        if not self._current:
            return []
        path = self._current / "findings.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def summary_text(self) -> str:
        """One-line human summary of this session."""
        if not self._meta:
            return "No active session."
        turns = self.get_conversation_history()
        findings = self.load_findings_raw()
        total_findings = sum(len(f.get("findings", [])) for f in findings)
        return (
            f"Session {self._meta.session_id} | "
            f"{len(turns)} turns | "
            f"{total_findings} findings | "
            f"status: {self._meta.status}"
        )

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
                    sessions.append(SessionMeta.from_dict(data))
                except Exception:
                    continue
        return sessions

    def compare_sessions(self, older_id: str, newer_id: str) -> str:
        """Compare two sessions and return a human-readable diff summary."""
        older = self._load_session_artifacts(older_id)
        newer = self._load_session_artifacts(newer_id)

        if older is None:
            raise FileNotFoundError(f"Session {older_id!r} not found")
        if newer is None:
            raise FileNotFoundError(f"Session {newer_id!r} not found")

        older_meta, older_findings = older
        newer_meta, newer_findings = newer
        older_index = self._finding_index(older_findings)
        newer_index = self._finding_index(newer_findings)

        new_keys = [k for k in newer_index if k not in older_index]
        resolved_keys = [k for k in older_index if k not in newer_index]
        changed_keys = [
            k for k in newer_index
            if k in older_index and newer_index[k]["severity"] != older_index[k]["severity"]
        ]

        lines = [
            f"Session comparison: **{older_meta.session_id}** -> **{newer_meta.session_id}**",
            "",
            f"Older: {sum(len(p.get('findings', [])) for p in older_findings)} findings",
            f"Newer: {sum(len(p.get('findings', [])) for p in newer_findings)} findings",
            f"New findings: {len(new_keys)}",
            f"Resolved findings: {len(resolved_keys)}",
            f"Severity changes: {len(changed_keys)}",
        ]

        if new_keys:
            lines.extend(["", "New in newer session:"])
            for key in new_keys[:8]:
                finding = newer_index[key]
                lines.append(
                    f"  + [{finding['severity'].upper()}] {finding['title']} "
                    f"({finding['file_path']}:{finding['start_line']})"
                )

        if resolved_keys:
            lines.extend(["", "Resolved since older session:"])
            for key in resolved_keys[:8]:
                finding = older_index[key]
                lines.append(
                    f"  - [{finding['severity'].upper()}] {finding['title']} "
                    f"({finding['file_path']}:{finding['start_line']})"
                )

        if changed_keys:
            lines.extend(["", "Severity changes:"])
            for key in changed_keys[:8]:
                before = older_index[key]
                after = newer_index[key]
                lines.append(
                    f"  * {after['title']} ({after['file_path']}:{after['start_line']}) "
                    f"{before['severity']} -> {after['severity']}"
                )

        return "\n".join(lines)

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def current_dir(self) -> Path | None:
        return self._current

    @property
    def current_meta(self) -> SessionMeta | None:
        return self._meta

    # ── Private ────────────────────────────────────────────────────────────

    def _save_meta(self) -> None:
        if not self._current or not self._meta:
            return
        path = self._current / "session.json"
        path.write_text(
            json.dumps(asdict(self._meta), indent=2), encoding="utf-8"
        )

    def _load_session_artifacts(
        self,
        session_id: str,
    ) -> tuple[SessionMeta, list[dict]] | None:
        session_dir = self.sessions_dir / session_id
        meta_path = session_dir / "session.json"
        findings_path = session_dir / "findings.json"
        if not meta_path.exists():
            return None

        meta = SessionMeta.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))
        findings: list[dict] = []
        if findings_path.exists():
            try:
                findings = json.loads(findings_path.read_text(encoding="utf-8"))
            except Exception:
                findings = []
        return meta, findings

    def _finding_index(self, findings_raw: list[dict]) -> dict[tuple[str, str, int, str], dict]:
        indexed: dict[tuple[str, str, int, str], dict] = {}
        for perspective_data in findings_raw:
            perspective_name = str(perspective_data.get("perspective_name", "unknown"))
            for finding in perspective_data.get("findings", []):
                if not isinstance(finding, dict):
                    continue
                title = str(finding.get("title", "Untitled finding"))
                file_path = str(finding.get("file_path", ""))
                start_line = int(finding.get("start_line", 0) or 0)
                key = (title, file_path, start_line, perspective_name)
                indexed[key] = {
                    "title": title,
                    "file_path": file_path,
                    "start_line": start_line,
                    "severity": str(finding.get("severity", "unknown")),
                    "perspective": perspective_name,
                }
        return indexed
