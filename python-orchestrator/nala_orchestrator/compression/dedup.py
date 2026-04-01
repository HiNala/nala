"""Near-duplicate content removal.

Fingerprints paragraphs/blocks using a rolling hash and removes blocks
that are >= SIMILARITY_THRESHOLD similar to a block already seen.

Strategy:
  - Split on blank lines into blocks.
  - Hash each block (normalised: lowercase, collapsed whitespace).
  - On second pass, skip blocks whose normalised form is within edit
    distance of an already-kept block (Jaccard on word sets, O(1) via sets).
  - Keep the first occurrence of near-duplicate content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Two blocks are "duplicates" if their word-set Jaccard similarity >= this.
_SIMILARITY_THRESHOLD = 0.80


@dataclass
class DedupResult:
    """Metrics from one deduplication pass."""
    blocks_in: int
    blocks_out: int
    duplicates_removed: int

    def summary(self) -> str:
        return (
            f"Dedup: {self.blocks_in} blocks → {self.blocks_out} "
            f"({self.duplicates_removed} duplicates removed)."
        )


def _normalise(block: str) -> str:
    """Lowercase, collapse whitespace — for comparison only."""
    return re.sub(r"\s+", " ", block.lower()).strip()


def _word_set(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", text))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class Deduplicator:
    """Removes near-duplicate paragraph blocks from text."""

    def __init__(self, threshold: float = _SIMILARITY_THRESHOLD) -> None:
        self._threshold = threshold

    def deduplicate(self, text: str) -> tuple[str, DedupResult]:
        """Return (deduplicated_text, metrics)."""
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        kept_sets: list[frozenset[str]] = []
        kept_blocks: list[str] = []
        duplicates = 0

        for block in blocks:
            norm = _normalise(block)
            ws = _word_set(norm)
            is_dup = any(_jaccard(ws, ks) >= self._threshold for ks in kept_sets)
            if is_dup:
                duplicates += 1
            else:
                kept_sets.append(ws)
                kept_blocks.append(block)

        return "\n\n".join(kept_blocks), DedupResult(
            blocks_in=len(blocks),
            blocks_out=len(kept_blocks),
            duplicates_removed=duplicates,
        )

    def deduplicate_history(
        self, history: list[dict]
    ) -> tuple[list[dict], int]:
        """Deduplicate assistant turns that repeat identical content.

        Returns (new_history, duplicates_removed).
        """
        seen: set[str] = set()
        result: list[dict] = []
        removed = 0

        for msg in history:
            content = msg.get("content", "")
            if msg.get("role") == "assistant":
                key = _normalise(content)[:300]
                if key in seen:
                    removed += 1
                    continue
                seen.add(key)
            result.append(msg)

        return result, removed
