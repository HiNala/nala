"""Context window management — token counting, compaction, and background summaries."""
from .background_summary import BackgroundSummary
from .compactor import Compactor
from .config import CompactionConfig
from .counter import TokenCounter, TokenUsage
from .detector import CompactionOpportunity, OpportunityDetector, Priority

__all__ = [
    "TokenCounter", "TokenUsage",
    "CompactionConfig",
    "OpportunityDetector", "CompactionOpportunity", "Priority",
    "Compactor",
    "BackgroundSummary",
]
