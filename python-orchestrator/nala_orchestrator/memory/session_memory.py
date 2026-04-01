"""Medium-term session memory (Layer 2).

Saves per-session summaries to .nala/memory/sessions/ and loads them on
session start to give the agent continuity across restarts.

Each summary is a markdown file that captures:
  - What the user was trying to accomplish
  - What was completed
  - Key decisions made
  - Current state when the session ended
  - Next steps
  - Files touched
  - Developer preferences observed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_SESSION_DIR_NAME = ".nala/memory/sessions"


@dataclass
class SessionRecord:
    """Structured record of one session."""
    session_id: str
    objective: str = ""
    completed: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    current_state: str = ""
    next_steps: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    developer_prefs: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_markdown(self) -> str:
        ts = self.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"## Session: {self.session_id}", f"*{ts}*", ""]
        if self.objective:
            lines += ["### Objective", self.objective, ""]
        if self.completed:
            lines += ["### Completed"] + [f"- {x}" for x in self.completed] + [""]
        if self.decisions:
            lines += ["### Key Decisions"] + [f"- {d}" for d in self.decisions] + [""]
        if self.current_state:
            lines += ["### Current State", self.current_state, ""]
        if self.next_steps:
            lines += ["### Next Steps"] + [f"- {s}" for s in self.next_steps] + [""]
        if self.modified_files:
            lines += ["### Modified Files"] + [f"- {f}" for f in self.modified_files] + [""]
        if self.developer_prefs:
            lines += ["### Developer Preferences Observed"] + [f"- {p}" for p in self.developer_prefs] + [""]
        return "\n".join(lines)

    def to_context_injection(self) -> str:
        """Return a compact context string for injecting into the next session."""
        parts = [f"[PREVIOUS SESSION: {self.session_id}]"]
        if self.objective:
            parts.append(f"Objective: {self.objective[:200]}")
        if self.completed:
            parts.append("Completed: " + "; ".join(self.completed[:5]))
        if self.current_state:
            parts.append(f"Last state: {self.current_state[:150]}")
        if self.next_steps:
            parts.append("Next steps: " + "; ".join(self.next_steps[:3]))
        if self.modified_files:
            parts.append("Files touched: " + ", ".join(self.modified_files[:6]))
        parts.append("[END PREVIOUS SESSION]")
        return "\n".join(parts)


class SessionMemory:
    """Saves and loads session summaries for medium-term continuity."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._dir = project_root / _SESSION_DIR_NAME
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Saving ────────────────────────────────────────────────────────────────

    def save(self, record: SessionRecord) -> Path:
        """Persist a SessionRecord to disk."""
        path = self._dir / f"{record.session_id}.md"
        path.write_text(record.to_markdown(), encoding="utf-8")
        log.debug("Session memory saved: %s", path.name)
        return path

    def build_and_save(
        self,
        session_id: str,
        history: list[dict],
        modified_files: Optional[list[str]] = None,
    ) -> SessionRecord:
        """Extract facts from conversation history and persist."""
        record = self._extract(session_id, history)
        if modified_files:
            record.modified_files = modified_files
        self.save(record)
        return record

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_latest(self, n: int = 1) -> list[SessionRecord]:
        """Load the N most recent session records."""
        files = sorted(
            self._dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:n]
        records: list[SessionRecord] = []
        for f in files:
            records.append(self._parse_markdown(f.stem, f.read_text(encoding="utf-8")))
        return records

    def load_for_files(self, file_paths: list[str], n: int = 5) -> list[str]:
        """Load sessions that mention any of the given file paths."""
        results: list[str] = []
        candidates = sorted(
            self._dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:20]
        for f in candidates:
            content = f.read_text(encoding="utf-8")
            if any(fp in content for fp in file_paths):
                results.append(content)
            if len(results) >= n:
                break
        return results

    def get_startup_injection(self) -> str:
        """Return a context string for the start of a new session.

        Loads the most recent session and formats it compactly.
        """
        recent = self.load_latest(1)
        if not recent:
            return ""
        return recent[0].to_context_injection()

    def list_sessions(self, n: int = 30) -> list[dict]:
        """List recent sessions with brief summaries for the /memory sessions command."""
        files = sorted(
            self._dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:n]
        result = []
        for f in files:
            lines = f.read_text(encoding="utf-8").splitlines()
            summary = next((l.lstrip("# ").strip() for l in lines if l.strip()), f.stem)
            result.append({"session_id": f.stem, "summary": summary[:80]})
        return result

    # ── Extraction ────────────────────────────────────────────────────────────

    def _extract(self, session_id: str, history: list[dict]) -> SessionRecord:
        user_msgs = [m["content"] for m in history if m.get("role") == "user"]
        asst_msgs = [m["content"] for m in history if m.get("role") == "assistant"]

        objective = user_msgs[0][:300].replace("\n", " ") if user_msgs else ""

        completed: list[str] = []
        for msg in asst_msgs:
            for line in msg.splitlines():
                line = line.strip()
                if len(line) > 10 and any(line.lower().startswith(kw) for kw in (
                    "applied", "created", "edited", "refactored", "fixed",
                    "added", "removed", "updated", "changed", "saved",
                    "built", "implemented", "wrote",
                )):
                    completed.append(line[:150])
                    if len(completed) >= 15:
                        break

        decisions: list[str] = []
        for msg in asst_msgs:
            for line in msg.splitlines():
                line = line.strip()
                if len(line) > 10 and any(line.lower().startswith(kw) for kw in (
                    "decided", "using ", "chose ", "will use", "approach:",
                )):
                    decisions.append(line[:150])
                    if len(decisions) >= 8:
                        break

        next_steps: list[str] = []
        if asst_msgs:
            for line in asst_msgs[-1].splitlines():
                line = line.strip()
                if len(line) > 10 and any(line.lower().startswith(kw) for kw in (
                    "next", "todo", "still need", "should", "need to",
                )):
                    next_steps.append(line[:120])
                    if len(next_steps) >= 5:
                        break

        current_state = (
            user_msgs[-1][:200].replace("\n", " ")
            if len(user_msgs) > 1 else ""
        )

        prefs: list[str] = []
        pref_kws = ("prefer", "prefers", "always use", "never use",
                    "style:", "format:", "convention:")
        for msg in asst_msgs:
            for line in msg.splitlines():
                line = line.strip()
                if len(line) > 10 and any(kw in line.lower() for kw in pref_kws):
                    prefs.append(line[:120])
                    if len(prefs) >= 5:
                        break

        return SessionRecord(
            session_id=session_id,
            objective=objective,
            completed=completed,
            decisions=decisions,
            current_state=current_state,
            next_steps=next_steps,
            developer_prefs=prefs,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    def _parse_markdown(self, session_id: str, text: str) -> SessionRecord:
        """Parse a saved markdown file back into a SessionRecord (best-effort)."""
        record = SessionRecord(session_id=session_id)
        current_section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## Session:"):
                pass
            elif stripped.startswith("### Objective"):
                current_section = "objective"
            elif stripped.startswith("### Completed"):
                current_section = "completed"
            elif stripped.startswith("### Key Decisions"):
                current_section = "decisions"
            elif stripped.startswith("### Current State"):
                current_section = "current_state"
            elif stripped.startswith("### Next Steps"):
                current_section = "next_steps"
            elif stripped.startswith("### Modified Files"):
                current_section = "modified_files"
            elif stripped.startswith("### Developer Preferences"):
                current_section = "developer_prefs"
            elif stripped.startswith("#"):
                current_section = ""
            elif stripped:
                item = stripped.lstrip("- ").strip()
                if not item:
                    continue
                if current_section == "objective":
                    record.objective = item
                elif current_section == "completed":
                    record.completed.append(item)
                elif current_section == "decisions":
                    record.decisions.append(item)
                elif current_section == "current_state":
                    record.current_state = item
                elif current_section == "next_steps":
                    record.next_steps.append(item)
                elif current_section == "modified_files":
                    record.modified_files.append(item)
                elif current_section == "developer_prefs":
                    record.developer_prefs.append(item)
        return record
