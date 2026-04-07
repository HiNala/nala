"""Handoff reader.

Loads the most recent handoff document and constructs a compact context
injection so the next session resumes where things left off.

Target: under 2 000 tokens for a typical handoff injection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .schema import HandoffDocument

log = logging.getLogger(__name__)

_HANDOFF_DIR = ".nala/memory/handoffs"
_CHAIN_FILE = "chain.json"
_MAX_INJECTION_CHARS = 6_000   # ~1 500 tokens


class HandoffReader:
    """Loads handoff documents and builds context injections."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._dir = project_root / _HANDOFF_DIR

    # ── Public API ────────────────────────────────────────────────────────────

    def get_startup_injection(self) -> str:
        """Return a compact context string for session startup.

        Returns empty string if no handoff exists.
        """
        doc = self.load_latest()
        if doc is None:
            return ""
        return self._build_injection(doc)

    def load_latest(self) -> HandoffDocument | None:
        """Load the most recent handoff document."""
        if not self._dir.exists():
            return None
        json_files = sorted(
            self._dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        # Skip chain.json
        json_files = [f for f in json_files if f.name != _CHAIN_FILE]
        for path in json_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return self._from_dict(data)
            except Exception as e:
                log.warning("Failed to load handoff %s: %s", path.name, e)
        return None

    def get_continuity_chain(self) -> list[dict]:
        """Return the ordered list of handoff summaries for history display."""
        chain_path = self._dir / _CHAIN_FILE
        if not chain_path.exists():
            return []
        try:
            data = json.loads(chain_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def has_unsaved_changes(self) -> bool:
        """Return True if the latest handoff has unsaved file changes."""
        doc = self.load_latest()
        if doc is None:
            return False
        return any(not mf.is_saved for mf in doc.modified_files)

    def format_history(self) -> str:
        """Format the continuity chain for display."""
        chain = self.get_continuity_chain()
        if not chain:
            return "No session history found."
        lines = ["Session History:"]
        for entry in chain[-10:]:
            ts = entry.get("timestamp", "?")[:16].replace("T", " ")
            sid = entry.get("session_id", "?")
            obj = entry.get("objective", "")[:60]
            done = entry.get("completed_count", 0)
            lines.append(f"  {ts}  [{sid}]  {obj}  ({done} actions)")
        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_injection(self, doc: HandoffDocument) -> str:
        """Build a compact context injection from a handoff document."""
        ts = doc.timestamp[:16].replace("T", " ")
        parts = [f"[RESUMING FROM HANDOFF — {ts} ({doc.trigger})]"]

        if doc.objective:
            parts.append(f"Objective: {doc.objective[:200]}")

        if doc.completed_actions:
            done = doc.completed_actions[-5:]
            parts.append("Completed: " + "; ".join(done))

        ip = doc.in_progress
        if not ip.is_empty():
            task_parts = [f"In progress: {ip.current_task[:150]}"]
            if ip.current_file:
                task_parts.append(f"File: {ip.current_file}")
            if ip.current_function:
                task_parts.append(f"Function: {ip.current_function}")
            parts.append(" | ".join(task_parts))
            if ip.pending_changes:
                parts.append("Pending: " + "; ".join(ip.pending_changes[:3]))
            if ip.blocking_issues:
                parts.append("Blockers: " + "; ".join(ip.blocking_issues[:2]))

        unsaved = [mf.path for mf in doc.modified_files if not mf.is_saved]
        if unsaved:
            parts.append("UNSAVED FILES: " + ", ".join(unsaved))
        touched = [mf.path for mf in doc.modified_files if mf.path]
        if touched:
            parts.append("Files touched: " + ", ".join(touched[:6]))

        if doc.decisions:
            parts.append("Key decisions: " + "; ".join(d.text[:80] for d in doc.decisions[:3]))

        if doc.next_steps:
            parts.append("Next steps: " + "; ".join(doc.next_steps[:3]))

        if doc.critical_context:
            parts.append("Context: " + "; ".join(doc.critical_context[:3]))

        parts.append("[END HANDOFF]")
        text = "\n".join(parts)

        # Truncate if over budget
        if len(text) > _MAX_INJECTION_CHARS:
            text = text[:_MAX_INJECTION_CHARS] + "\n...[truncated]\n[END HANDOFF]"

        return text

    def _from_dict(self, data: dict) -> HandoffDocument:
        """Deserialise a HandoffDocument from a raw dict."""
        from .schema import Decision, InProgressState, ModifiedFile
        ip_data = data.get("in_progress", {})
        ip = InProgressState(
            current_task=ip_data.get("current_task", ""),
            current_file=ip_data.get("current_file", ""),
            current_function=ip_data.get("current_function", ""),
            pending_changes=ip_data.get("pending_changes", []),
            blocking_issues=ip_data.get("blocking_issues", []),
        )
        modified = [
            ModifiedFile(
                path=mf.get("path", ""),
                change_summary=mf.get("change_summary", ""),
                is_saved=mf.get("is_saved", True),
                has_tests=mf.get("has_tests", False),
            )
            for mf in data.get("modified_files", [])
        ]
        decisions = [
            Decision(
                text=d.get("text", ""),
                rationale=d.get("rationale", ""),
                affected_files=d.get("affected_files", []),
            )
            for d in data.get("decisions", [])
        ]
        return HandoffDocument(
            timestamp=data.get("timestamp", ""),
            session_id=data.get("session_id", ""),
            trigger=data.get("trigger", "manual"),
            objective=data.get("objective", ""),
            completed_actions=data.get("completed_actions", []),
            in_progress=ip,
            modified_files=modified,
            decisions=decisions,
            next_steps=data.get("next_steps", []),
            critical_context=data.get("critical_context", []),
            constraints=data.get("constraints", []),
        )
