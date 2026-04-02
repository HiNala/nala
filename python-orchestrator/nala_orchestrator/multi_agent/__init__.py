"""Multi-agent orchestration engine.

Coordinates multiple AI agents working on different parts of a codebase
simultaneously through shared task lists, file locking, and message passing.

Architecture (inspired by open-multi-agent's event-driven patterns):
  - LeadAgent: Coordinates, decomposes work, synthesises results
  - TaskList:  Shared SQLite-backed task queue with dependency resolution
  - FileLocks: Prevents concurrent file modifications
  - MessageBus: Agents send targeted or broadcast messages
  - Spawner:   Creates worker agent instances as async tasks
"""

from .decomposer import TaskDecomposer, TaskPlan
from .file_locks import FileLockRegistry
from .lead import LeadAgent
from .messages import AgentMessage, MessageBus
from .spawner import AgentSpawner, WorkerResult
from .task_list import SharedTaskList, Task, TaskStatus

__all__ = [
    "Task", "TaskStatus", "SharedTaskList",
    "FileLockRegistry",
    "MessageBus", "AgentMessage",
    "AgentSpawner", "WorkerResult",
    "TaskPlan", "TaskDecomposer",
    "LeadAgent",
]
