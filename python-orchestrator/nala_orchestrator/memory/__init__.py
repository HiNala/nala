"""Hierarchical memory system for Nala.

Three tiers:
  Layer 1 (Short-term):  Working context — current conversation + injected context.
  Layer 2 (Medium-term): Session memory — per-session summaries saved to disk.
  Layer 3 (Long-term):   Knowledge base — accumulated project facts.
"""

from .short_term import ShortTermMemory
from .session_memory import SessionMemory, SessionRecord
from .knowledge import KnowledgeBase
from .compression import SmartStrip

__all__ = ["ShortTermMemory", "SessionMemory", "SessionRecord", "KnowledgeBase", "SmartStrip"]
