"""Long-term project knowledge base (Layer 3).

Accumulates facts about the project across sessions in .nala/memory/knowledge/.
Facts are organized into topic files by category:
  - architecture.md   — system design, patterns, tech choices
  - conventions.md    — coding style, naming, error handling
  - tech_debt.md      — known issues, hotspots, needed refactors
  - developer_prefs.md — how this developer likes to work
  - analysis_history.md — trends from analysis sessions
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_KB_DIR_NAME = ".nala/memory/knowledge"

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "architecture.md": [
        "architecture", "design", "pattern", "structure", "layer",
        "component", "service", "module", "system", "framework", "crate",
    ],
    "conventions.md": [
        "convention", "style", "naming", "format", "standard",
        "snake_case", "camelcase", "pascalcase", "indent", "docstring",
        "type hint", "error handling",
    ],
    "tech_debt.md": [
        "complexity", "cyclomatic", "refactor", "debt", "hotspot",
        "todo", "fixme", "hack", "workaround", "brittle", "coupling",
        "circular", "duplicate",
    ],
    "developer_prefs.md": [
        "prefer", "prefers", "always", "never", "like", "dislikes",
        "wants", "expects", "usually", "typically",
    ],
    "analysis_history.md": [
        "finding", "analysis", "scan", "session", "perspective",
        "report", "mission", "severity", "critical", "high",
    ],
}


class KnowledgeBase:
    """Persistent long-term project knowledge that survives across sessions."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._kb_dir = project_root / _KB_DIR_NAME
        self._kb_dir.mkdir(parents=True, exist_ok=True)

    # ── Fact management ───────────────────────────────────────────────────────

    def add_fact(self, fact: str, category: Optional[str] = None) -> None:
        """Add a single fact to the knowledge base."""
        fact = fact.strip()
        if not fact or len(fact) < 10:
            return
        cat_file = category or self._classify(fact)
        path = self._kb_dir / cat_file
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if fact in existing:
            return  # already known
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {fact}\n")
        log.debug("Knowledge fact added → %s: %.60s", cat_file, fact)

    def add_facts(self, facts: list[str], category: Optional[str] = None) -> None:
        for fact in facts:
            self.add_fact(fact, category)

    def remove_fact(self, topic: str) -> int:
        """Remove all facts containing `topic` from all categories. Returns count removed."""
        removed = 0
        for path in self._kb_dir.glob("*.md"):
            lines = path.read_text(encoding="utf-8").splitlines()
            new_lines = [l for l in lines if topic.lower() not in l.lower()]
            if len(new_lines) != len(lines):
                path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                removed += len(lines) - len(new_lines)
        return removed

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_for_context(self, query: str = "", max_chars: int = 4_000) -> str:
        """Load relevant knowledge for a query within the char budget."""
        if not query:
            return self._load_all(max_chars)

        query_lower = query.lower()
        scored: list[tuple[float, str, str]] = []
        for cat_file in sorted(self._kb_dir.glob("*.md")):
            content = cat_file.read_text(encoding="utf-8").strip()
            if not content:
                continue
            keywords = _CATEGORY_KEYWORDS.get(cat_file.name, [])
            hits = sum(1 for kw in keywords if kw in query_lower)
            if cat_file.name == "developer_prefs.md":
                hits += 2  # always slightly relevant
            scored.append((hits, cat_file.name, content))

        scored.sort(key=lambda x: -x[0])
        parts: list[str] = []
        total = 0
        for _, name, content in scored:
            if total + len(content) > max_chars:
                break
            parts.append(f"### {name.replace('.md', '')}\n{content}")
            total += len(content)

        return "\n\n".join(parts)

    def get_summary(self) -> str:
        """Return a brief human-readable summary of stored knowledge."""
        lines = ["[PROJECT KNOWLEDGE BASE]"]
        total_facts = 0
        for path in sorted(self._kb_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            count = len([l for l in content.splitlines() if l.strip().startswith("-")])
            total_facts += count
            lines.append(f"  {path.stem}: {count} fact{'s' if count != 1 else ''}")
        lines.append(f"  Total: {total_facts} facts across {len(lines) - 1} categories")
        lines.append("[END KNOWLEDGE BASE]")
        return "\n".join(lines)

    # ── Extraction from session memory ────────────────────────────────────────

    def extract_from_session(self, session_md: str, max_per_session: int = 5) -> None:
        """Extract durable facts from a session markdown and add to KB."""
        for line in session_md.splitlines():
            line = line.strip().lstrip("- ").strip()
            if len(line) < 15:
                continue
            cat = self._classify(line)
            # Only ingest lines from structured sections — skip headings
            if line.startswith("#"):
                continue
            self.add_fact(line[:200], category=cat)
            max_per_session -= 1
            if max_per_session <= 0:
                break

    def consolidate(self, max_facts_per_category: int = 100) -> None:
        """Remove duplicate facts and trim oversized categories."""
        for path in self._kb_dir.glob("*.md"):
            lines = path.read_text(encoding="utf-8").splitlines()
            seen: set[str] = set()
            deduped: list[str] = []
            for line in lines:
                key = line.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    deduped.append(line)
            deduped = deduped[:max_facts_per_category]
            path.write_text("\n".join(deduped) + "\n", encoding="utf-8")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _classify(self, text: str) -> str:
        text_lower = text.lower()
        best_cat = "analysis_history.md"
        best_hits = 0
        for cat_file, keywords in _CATEGORY_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits > best_hits:
                best_hits = hits
                best_cat = cat_file
        return best_cat

    def _load_all(self, max_chars: int) -> str:
        parts: list[str] = []
        total = 0
        for path in sorted(self._kb_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            if total + len(content) > max_chars:
                break
            parts.append(f"### {path.stem}\n{content}")
            total += len(content)
        return "\n\n".join(parts)
