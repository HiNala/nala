"""Session handoff and continuity protocol.

Ensures zero-loss continuity when a context window fills up or a session
ends.  Before compaction or close, Nala writes a structured handoff document.
When the next session starts, it reads the document and resumes seamlessly.
"""

from .reader import HandoffReader
from .schema import Decision, HandoffDocument, InProgressState, ModifiedFile
from .writer import HandoffWriter

__all__ = [
    "HandoffDocument", "InProgressState", "ModifiedFile", "Decision",
    "HandoffWriter", "HandoffReader",
]
