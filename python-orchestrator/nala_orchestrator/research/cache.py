"""Research cache — persists research artifacts to .nala/agent/research/."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import ResearchResult

log = logging.getLogger("nala.research.cache")


class ResearchCache:
    """Disk-backed cache of research results under .nala/agent/research/."""

    def __init__(self, project_root: Path) -> None:
        self._dir = Path(project_root) / ".nala" / "agent" / "research"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, ResearchResult] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        for path in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                result = ResearchResult.from_dict(data)
                key = self._key(result.question)
                self._memory[key] = result
            except Exception:
                log.debug("Skipping unreadable research cache file: %s", path.name)

    @staticmethod
    def _key(question: str) -> str:
        return question.strip().lower()[:120]

    def lookup(self, question: str) -> ResearchResult | None:
        return self._memory.get(self._key(question))

    def store(self, result: ResearchResult) -> None:
        key = self._key(result.question)
        self._memory[key] = result
        path = self._dir / f"{result.query_id}.json"
        try:
            path.write_text(
                json.dumps(result.to_dict(), indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            log.warning("Failed to persist research result: %s", e)

    def recent(self, limit: int = 5) -> list[ResearchResult]:
        all_results = sorted(
            self._memory.values(),
            key=lambda r: r.completed_at,
            reverse=True,
        )
        return all_results[:limit]

    def clear(self) -> None:
        self._memory.clear()
        for path in self._dir.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                pass
