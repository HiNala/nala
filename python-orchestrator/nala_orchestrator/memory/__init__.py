"""Hierarchical memory system for Nala.

Three tiers:
  Layer 1 (Short-term):  Working context — current conversation + injected context.
  Layer 2 (Medium-term): Session memory — per-session summaries saved to disk.
  Layer 3 (Long-term):   Knowledge base — accumulated project facts.
"""

from .compression import SmartStrip
from .knowledge import KnowledgeBase
from .session_memory import SessionMemory, SessionRecord
from .short_term import ShortTermMemory

__all__ = ["ShortTermMemory", "SessionMemory", "SessionRecord", "KnowledgeBase", "SmartStrip"]
