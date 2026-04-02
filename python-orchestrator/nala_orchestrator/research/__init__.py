"""Research package — bounded, attributable web research for /agent workflows."""

from .models import Citation, ResearchQuery, ResearchResult
from .service import ResearchService

__all__ = ["Citation", "ResearchQuery", "ResearchResult", "ResearchService"]
