"""LLM enrichment for review findings.

Takes a VerifiedFinding and uses a cheap LLM sub-call to rewrite the
instruction to be maximally specific: naming exact functions, variables, and
the precise change to make. Falls back to the original text if no provider.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .models import VerifiedFinding

if TYPE_CHECKING:
    from nala_orchestrator.llm.provider import BaseLLMProvider

log = logging.getLogger("nala.review.enricher")

_ENRICH_PROMPT = """\
You are a code review assistant. A static analysis tool has found the following \
issue. Rewrite the instruction to be maximally specific and actionable for a \
coding agent: name the exact functions, variables, identifiers, and the precise \
change required. Be concrete. Keep the rewrite under 80 words.

File: {file_path}
Lines: {start_line}-{end_line}
Rule: {rule_name}
Original description: {description}
Original instruction: {instruction}

Code context:
```
{code_snippet}
```

Rewritten instruction (one specific, agent-ready sentence):"""


class Enricher:
    def __init__(self, provider: BaseLLMProvider | None = None):
        self.provider = provider

    async def enrich(
        self,
        finding: VerifiedFinding,
        file_content: str,
    ) -> VerifiedFinding:
        """Enrich the finding instruction with an LLM call if a provider is available."""
        if not self.provider:
            return finding

        try:
            snippet = _extract_snippet(file_content, finding.start_line, finding.end_line)
            prompt = _ENRICH_PROMPT.format(
                file_path=finding.file_path,
                start_line=finding.start_line,
                end_line=finding.end_line,
                rule_name=finding.rule_name,
                description=finding.description,
                instruction=finding.instruction,
                code_snippet=snippet,
            )

            from nala_orchestrator.llm.provider import LLMMessage  # local import avoids cycle

            response = await self.provider.chat(
                messages=[LLMMessage(role="user", content=prompt)],
                system_prompt=(
                    "You are a precise code review assistant. Output only the rewritten "
                    "instruction — no preamble, no bullet points, no markdown."
                ),
                max_tokens=150,
            )
            enriched = response.content.strip()
            if enriched:
                finding.enriched_description = enriched
        except Exception as exc:
            # Enrichment is best-effort — never fail the review pipeline
            log.debug("LLM enrichment failed for %s: %s", finding.rule_name, exc)

        return finding


def _extract_snippet(file_content: str, start_line: int, end_line: int, context: int = 3) -> str:
    """Return the relevant lines with a few lines of surrounding context."""
    lines = file_content.splitlines()
    lo = max(0, start_line - 1 - context)
    hi = min(len(lines), end_line + context)
    return "\n".join(lines[lo:hi])
