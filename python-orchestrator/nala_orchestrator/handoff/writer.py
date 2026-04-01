"""Handoff writer.

Called before compaction, session end, or manual /handoff to capture
exactly where things stand so the next session can resume seamlessly.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .schema import (
    Decision, HandoffDocument, InProgressState, ModifiedFile,
)

log = logging.getLogger(__name__)

_HANDOFF_DIR = ".nala/memory/handoffs"
_CHAIN_FILE = "chain.json"


class HandoffWriter:
    """Extracts session state and persists handoff documents."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._dir = project_root / _HANDOFF_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def write(
        self,
        session_id: str,
        trigger: str,
        history: list[dict],
        modified_files: Optional[list[str]] = None,
    ) -> HandoffDocument:
        """Extract handoff state from conversation history and save."""
        doc = HandoffDocument.create(session_id, trigger)
        self._populate(doc, history, modified_files or [])

        # Validate and warn but never block
        for warning in doc.validate():
            log.warning("Handoff validation: %s", warning)

        # Compress if over budget
        if doc.token_estimate() > 3_000:
            doc = self._compress(doc)

        self._save(doc)
        self._update_chain(doc)
        return doc

    # ── Internal ──────────────────────────────────────────────────────────────

    def _populate(
        self,
        doc: HandoffDocument,
        history: list[dict],
        modified_files: list[str],
    ) -> None:
        user_msgs = [m["content"] for m in history if m.get("role") == "user"]
        asst_msgs = [m["content"] for m in history if m.get("role") == "assistant"]

        # Objective: first user message
        if user_msgs:
            doc.objective = user_msgs[0][:300].replace("\n", " ")

        # Completed actions: action verbs from assistant messages
        for msg in asst_msgs:
            for line in msg.splitlines():
                stripped = line.strip()
                if len(stripped) > 10 and any(stripped.lower().startswith(kw) for kw in (
                    "created", "edited", "fixed", "added", "removed", "updated",
                    "changed", "applied", "refactored", "deleted", "wrote",
                    "implemented", "built", "saved", "committed",
                )):
                    doc.completed_actions.append(stripped[:150])
                    if len(doc.completed_actions) >= 20:
                        break

        # In-progress: last user message → current task
        if user_msgs and len(user_msgs) > 1:
            last = user_msgs[-1][:200].replace("\n", " ")
            doc.in_progress.current_task = last

        # Modified files
        for fp in modified_files:
            doc.modified_files.append(ModifiedFile(path=fp, change_summary="modified"))

        # Also try to extract file paths from assistant messages
        import re
        file_re = re.compile(r'`([a-zA-Z0-9_./\-]+\.[a-zA-Z]{1,5})`')
        seen_files: set[str] = {mf.path for mf in doc.modified_files}
        for msg in asst_msgs[-3:]:
            for match in file_re.finditer(msg):
                fp = match.group(1)
                if fp not in seen_files and len(fp) > 3:
                    doc.modified_files.append(ModifiedFile(path=fp, change_summary="mentioned"))
                    seen_files.add(fp)
                    if len(doc.modified_files) >= 10:
                        break

        # Decisions
        for msg in asst_msgs:
            for line in msg.splitlines():
                stripped = line.strip()
                if len(stripped) > 10 and any(stripped.lower().startswith(kw) for kw in (
                    "decided", "using ", "chose ", "will use", "approach:",
                )):
                    doc.decisions.append(Decision(text=stripped[:150]))
                    if len(doc.decisions) >= 8:
                        break

        # Next steps: last assistant message
        if asst_msgs:
            for line in asst_msgs[-1].splitlines():
                stripped = line.strip()
                if len(stripped) > 10 and any(stripped.lower().startswith(kw) for kw in (
                    "next", "todo", "still need", "should", "need to",
                )):
                    doc.next_steps.append(stripped[:120])
                    if len(doc.next_steps) >= 5:
                        break

        # Critical context: any line mentioning metrics or identifiers
        import re
        metric_re = re.compile(r'\bcc\s*=\s*\d+|\bsloc\s*=|\bcomplexity\b', re.I)
        for msg in asst_msgs[-5:]:
            for line in msg.splitlines():
                if metric_re.search(line) and len(line.strip()) > 15:
                    doc.critical_context.append(line.strip()[:150])
                    if len(doc.critical_context) >= 5:
                        break

    def _compress(self, doc: HandoffDocument) -> HandoffDocument:
        """Trim oversized sections to bring the document under 3000 tokens."""
        doc.completed_actions = doc.completed_actions[:10]
        doc.decisions = doc.decisions[:5]
        doc.critical_context = doc.critical_context[:3]
        doc.modified_files = doc.modified_files[:8]
        doc.next_steps = doc.next_steps[:3]
        return doc

    def _save(self, doc: HandoffDocument) -> None:
        ts_safe = doc.timestamp[:19].replace(":", "-").replace("T", "_")
        json_path = self._dir / f"{ts_safe}.json"
        md_path = self._dir / f"{ts_safe}.md"
        json_path.write_text(doc.to_json(), encoding="utf-8")
        md_path.write_text(doc.to_markdown(), encoding="utf-8")
        log.info("Handoff saved: %s", json_path.name)

    def _update_chain(self, doc: HandoffDocument) -> None:
        chain_path = self._dir / _CHAIN_FILE
        chain: list[dict] = []
        if chain_path.exists():
            try:
                chain = json.loads(chain_path.read_text(encoding="utf-8"))
            except Exception:
                chain = []
        chain.append({
            "timestamp": doc.timestamp,
            "session_id": doc.session_id,
            "trigger": doc.trigger,
            "objective": doc.objective[:100],
            "completed_count": len(doc.completed_actions),
        })
        # Keep last 50 entries
        chain = chain[-50:]
        chain_path.write_text(json.dumps(chain, indent=2), encoding="utf-8")
