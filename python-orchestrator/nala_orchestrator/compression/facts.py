"""Fact extraction and preservation.

Scans text for factual statements and ensures they survive compression
intact. A "fact" here is a sentence containing:
  - File paths (absolute or relative)
  - Function/class/method names (dotted identifiers)
  - Line numbers or numeric metrics
  - Error messages (contains "Error:", "Exception:", "warning:")
  - Key-value assertions ("X is Y", "X = Y", "X: Y")

The FactExtractor can be used to:
  1. Audit compressed output and verify no facts were lost.
  2. Extract facts from a conversation turn for injection into future context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Fact detection patterns ───────────────────────────────────────────────────

_PATH_RE = re.compile(
    r"(?:[a-zA-Z_][a-zA-Z0-9_/\-]*(?:/[a-zA-Z0-9_.\-]+)+|"
    r"/[a-zA-Z0-9_./\-]+|"
    r"[A-Z]:\\[^\s,;\"']+)"
)

_DOTTED_RE = re.compile(
    r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*){1,}"
)

_LINE_RE = re.compile(r"\bline\s+\d+\b|\bL\d+\b|:\d+:\d*", re.IGNORECASE)

_ERROR_RE = re.compile(
    r"\b(?:Error|Exception|Warning|FAIL|FAILED|assert)[\s:]",
    re.IGNORECASE,
)

_METRIC_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|s|kb|mb|gb|%|tokens?|files?|lines?|chars?)\b",
    re.IGNORECASE,
)


@dataclass
class Fact:
    """A single extracted fact."""
    text: str
    category: str  # path | symbol | location | error | metric | assertion


@dataclass
class FactSet:
    """All facts extracted from a text block."""
    facts: list[Fact] = field(default_factory=list)

    def paths(self) -> list[str]:
        return [f.text for f in self.facts if f.category == "path"]

    def symbols(self) -> list[str]:
        return [f.text for f in self.facts if f.category == "symbol"]

    def errors(self) -> list[str]:
        return [f.text for f in self.facts if f.category == "error"]

    def all_identifiers(self) -> set[str]:
        return {f.text for f in self.facts if f.category in ("path", "symbol")}

    def as_context_block(self) -> str:
        """Format facts as a compact context injection."""
        if not self.facts:
            return ""
        lines = ["[EXTRACTED FACTS]"]
        for f in self.facts:
            lines.append(f"  [{f.category}] {f.text}")
        lines.append("[END FACTS]")
        return "\n".join(lines)


class FactExtractor:
    """Extracts facts from text for audit and context injection."""

    def extract(self, text: str) -> FactSet:
        """Extract all facts from a text block."""
        facts: list[Fact] = []
        seen: set[str] = set()

        def add(text: str, cat: str) -> None:
            key = text.strip()
            if key and key not in seen:
                seen.add(key)
                facts.append(Fact(text=key, category=cat))

        # Paths
        for m in _PATH_RE.finditer(text):
            add(m.group(0), "path")

        # Dotted identifiers (skip if already captured as path)
        for m in _DOTTED_RE.finditer(text):
            tok = m.group(0)
            if not any(tok in p for p in seen):
                add(tok, "symbol")

        # Line references
        for m in _LINE_RE.finditer(text):
            add(m.group(0), "location")

        # Error messages — extract the containing sentence
        for m in _ERROR_RE.finditer(text):
            start = max(0, text.rfind("\n", 0, m.start()) + 1)
            end = text.find("\n", m.end())
            if end == -1:
                end = len(text)
            sentence = text[start:end].strip()[:200]
            add(sentence, "error")

        # Metrics
        for m in _METRIC_RE.finditer(text):
            add(m.group(0), "metric")

        return FactSet(facts=facts)

    def audit(self, original: str, compressed: str) -> list[str]:
        """Return a list of facts present in original but absent in compressed.

        An empty list means no factual loss (compression is safe).
        """
        orig_facts = self.extract(original)
        lost: list[str] = []
        for ident in orig_facts.all_identifiers():
            if ident not in compressed:
                lost.append(ident)
        for err in orig_facts.errors():
            # Check the key noun phrase is still present
            nouns = re.findall(r"\b[A-Z][a-z]+Error\b|\b[A-Z]+_[A-Z]+\b", err)
            for noun in nouns:
                if noun not in compressed:
                    lost.append(noun)
        return lost

    def extract_from_history(
        self,
        history: list[dict],
        max_facts: int = 50,
    ) -> FactSet:
        """Extract facts from a conversation history."""
        combined = "\n".join(
            m.get("content", "") for m in history
            if m.get("role") in ("user", "assistant")
        )
        fs = self.extract(combined)
        fs.facts = fs.facts[:max_facts]
        return fs
