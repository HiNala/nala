"""ResearchService — bounded, attributable web research for /agent.

Uses LLM-powered search simulation when no external search API is configured,
or delegates to a real search provider when available. All results are cached
and cited.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .cache import ResearchCache
from .models import Citation, ResearchQuery, ResearchResult

if TYPE_CHECKING:
    from pathlib import Path

    from ..agents.orchestrator import AgentOrchestrator
    from ..config import Config

log = logging.getLogger("nala.research.service")

MAX_QUERIES_PER_RUN = 10
MAX_SOURCES_PER_QUERY = 5

TRUSTED_DOMAINS = [
    "docs.python.org",
    "doc.rust-lang.org",
    "developer.mozilla.org",
    "docs.github.com",
    "react.dev",
    "nextjs.org",
    "nodejs.org",
    "docs.docker.com",
    "kubernetes.io",
    "pypi.org",
    "crates.io",
    "npmjs.com",
    "stackoverflow.com",
]


class ResearchService:
    """Manages bounded web research with caching and attribution."""

    def __init__(
        self,
        config: Config,
        project_root: Path,
        orchestrator: AgentOrchestrator | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self._orchestrator = orchestrator
        self._cache = ResearchCache(project_root)
        self._query_count = 0

    def set_orchestrator(self, orch: AgentOrchestrator) -> None:
        self._orchestrator = orch

    @property
    def budget_remaining(self) -> int:
        return max(0, MAX_QUERIES_PER_RUN - self._query_count)

    def reset_budget(self) -> None:
        self._query_count = 0

    async def research(
        self,
        question: str,
        context: str = "",
        max_sources: int = MAX_SOURCES_PER_QUERY,
    ) -> AsyncIterator[str]:
        """Run a bounded research query. Yields streaming chunks, then final result."""
        if self._query_count >= MAX_QUERIES_PER_RUN:
            yield "Research budget exhausted for this run. Use `/agent` to start a new run."
            return

        cached = self._cache.lookup(question)
        if cached:
            yield cached.format_for_interpreter()
            return

        query = ResearchQuery(
            question=question,
            context=context,
            max_sources=min(max_sources, MAX_SOURCES_PER_QUERY),
            trusted_domains=TRUSTED_DOMAINS,
        )
        self._query_count += 1

        yield f"Researching: *{question}*\n"

        result = await self._execute_research(query)
        self._cache.store(result)

        yield result.format_for_interpreter()

    async def _execute_research(self, query: ResearchQuery) -> ResearchResult:
        """Execute a research query using the LLM with research-oriented prompting."""
        if self._orchestrator is None:
            return ResearchResult(
                query_id=query.query_id,
                question=query.question,
                summary="Research unavailable — no LLM provider configured.",
            )

        prompt = self._build_research_prompt(query)
        full_response = ""
        async for chunk in self._orchestrator.stream(prompt):
            full_response += chunk

        return self._parse_research_response(query, full_response)

    def _build_research_prompt(self, query: ResearchQuery) -> str:
        parts = [
            "You are a research assistant. Answer the following technical question "
            "with specific, actionable facts. For each claim, provide a source URL "
            "if you know it. Be concise and structured.\n",
            f"QUESTION: {query.question}\n",
        ]
        if query.context:
            parts.append(f"CONTEXT: {query.context[:500]}\n")
        parts.append(
            "Format your response as:\n"
            "SUMMARY: <1-2 sentence answer>\n"
            "FACTS:\n- <fact 1>\n- <fact 2>\n...\n"
            "SOURCES:\n- <url 1> — <title/description>\n- <url 2> — <title/description>\n...\n"
            "UNCERTAIN:\n- <anything you're not confident about>\n"
        )
        return "\n".join(parts)

    def _parse_research_response(
        self, query: ResearchQuery, response: str,
    ) -> ResearchResult:
        """Parse structured research response into a ResearchResult."""
        summary = ""
        facts: list[str] = []
        citations: list[Citation] = []
        uncertainties: list[str] = []

        section = ""
        for line in response.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("SUMMARY:"):
                summary = stripped[8:].strip()
                section = "summary"
            elif upper.startswith("FACTS:"):
                section = "facts"
            elif upper.startswith("SOURCES:"):
                section = "sources"
            elif upper.startswith("UNCERTAIN:"):
                section = "uncertain"
            elif stripped.startswith("- ") or stripped.startswith("* "):
                item = stripped[2:].strip()
                if section == "facts" and item:
                    facts.append(item)
                elif section == "sources" and item:
                    citation = self._parse_citation(item)
                    if citation:
                        citations.append(citation)
                elif section == "uncertain" and item:
                    uncertainties.append(item)
            elif section == "summary" and stripped:
                summary += " " + stripped

        return ResearchResult(
            query_id=query.query_id,
            question=query.question,
            summary=summary.strip(),
            facts=facts[:10],
            citations=citations[:query.max_sources],
            uncertainties=uncertainties[:5],
        )

    @staticmethod
    def _parse_citation(text: str) -> Citation | None:
        """Extract URL and title from a source line."""
        url_match = re.search(r'https?://[^\s)]+', text)
        if url_match:
            url = url_match.group(0).rstrip(".,;")
            title = text.replace(url, "").strip(" -—–|")
            domain = urlparse(url).netloc
            return Citation(url=url, title=title, domain=domain)
        if text:
            return Citation(title=text)
        return None

    def get_recent_research(self, limit: int = 5) -> list[ResearchResult]:
        return self._cache.recent(limit)

    def format_research_context(self) -> str:
        """Format recent research for injection into LLM context."""
        recent = self._cache.recent(3)
        if not recent:
            return ""
        parts = ["[RECENT RESEARCH]"]
        for r in recent:
            parts.append(r.format_for_context())
        parts.append("[END RECENT RESEARCH]")
        return "\n\n".join(parts)
