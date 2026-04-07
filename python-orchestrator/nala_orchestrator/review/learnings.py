from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass
class Learning:
    rule_name: str
    file_pattern: str     # e.g., "*.test.tsx" or "src/migrations/**"
    dismissed_pattern: str # The specific pattern that was a false positive
    reason: str           # Why it was dismissed
    created_at: str


class LearningsDB:
    def __init__(self, nala_dir: Path):
        self.db_path = nala_dir / "review" / "learnings.json"
        self.learnings: list[Learning] = []
        self._load()

    def _load(self) -> None:
        if self.db_path.exists():
            try:
                data = json.loads(self.db_path.read_text(encoding="utf-8"))
                for item in data.get("learnings", []):
                    self.learnings.append(Learning(**item))
            except Exception:
                pass

    def save(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"learnings": [asdict(learning) for learning in self.learnings]}
        self.db_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_dismissed(self, rule_name: str, file_path: str, context_str: str) -> bool:
        """Check if a finding matches a previously dismissed pattern."""
        import fnmatch

        # Normalise separators so patterns work on Windows too
        norm_path = file_path.replace("\\", "/")

        for learning in self.learnings:
            if learning.rule_name != rule_name:
                continue
            pattern = learning.file_pattern.replace("\\", "/")
            # Match against full path OR just the tail (relative path)
            if fnmatch.fnmatch(norm_path, pattern) or fnmatch.fnmatch(
                norm_path, f"*/{pattern}"
            ):
                if learning.dismissed_pattern in context_str:
                    return True
        return False
