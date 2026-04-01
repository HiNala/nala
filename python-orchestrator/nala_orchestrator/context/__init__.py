"""Context window management — token counting, compaction, and background summaries."""
from .counter import TokenCounter, TokenUsage
from .config import CompactionConfig
from .detector import OpportunityDetector, CompactionOpportunity, Priority
from .compactor import Compactor
from .background_summary import BackgroundSummary

__all__ = [
    "TokenCounter", "TokenUsage",
    "CompactionConfig",
    "OpportunityDetector", "CompactionOpportunity", "Priority",
    "Compactor",
    "BackgroundSummary",
]
