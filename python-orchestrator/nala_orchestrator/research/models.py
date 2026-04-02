"""Data models for web research queries, results, and citations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Citation:
    """A single attributed source."""
    url: str = ""
    title: str = ""
    snippet: str = ""
    domain: str = ""
    accessed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def short(self) -> str:
        label = self.title or self.domain or self.url[:60]
        return f"[{label}]({self.url})" if self.url else label

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "domain": self.domain,
            "accessed_at": self.accessed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Citation:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ResearchQuery:
    """A bounded research request."""
    query_id: str = field(default_factory=lambda: f"rq-{uuid.uuid4().hex[:8]}")
    question: str = ""
    context: str = ""
    max_sources: int = 5
    trusted_domains: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "question": self.question,
            "context": self.context,
            "max_sources": self.max_sources,
            "trusted_domains": self.trusted_domains,
            "created_at": self.created_at,
        }


@dataclass
class ResearchResult:
    """Aggregated research output with citations and extracted facts."""
    query_id: str = ""
    question: str = ""
    summary: str = ""
    facts: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    completed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def format_for_interpreter(self) -> str:
        """Concise summary for the main terminal."""
        lines = [f"**Research:** {self.question}"]
        if self.summary:
            lines.append(self.summary)
        if self.facts:
            lines.append("\n**Key facts:**")
            for fact in self.facts[:5]:
                lines.append(f"  - {fact}")
        if self.citations:
            lines.append(f"\n**Sources:** ({len(self.citations)} consulted)")
            for c in self.citations[:5]:
                lines.append(f"  - {c.short()}")
        if self.uncertainties:
            lines.append("\n**Uncertain:**")
            for u in self.uncertainties[:3]:
                lines.append(f"  - {u}")
        return "\n".join(lines)

    def format_for_context(self) -> str:
        """Compact version for injection into LLM context."""
        parts = [f"[RESEARCH: {self.question}]"]
        if self.summary:
            parts.append(self.summary[:500])
        if self.facts:
            parts.append("Facts: " + "; ".join(self.facts[:5]))
        if self.uncertainties:
            parts.append("Uncertain: " + "; ".join(self.uncertainties[:3]))
        parts.append("[END RESEARCH]")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "question": self.question,
            "summary": self.summary,
            "facts": self.facts,
            "citations": [c.to_dict() for c in self.citations],
            "uncertainties": self.uncertainties,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ResearchResult:
        d = dict(d)
        d["citations"] = [Citation.from_dict(c) for c in d.get("citations", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
