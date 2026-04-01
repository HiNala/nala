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

from .task_list import Task, TaskStatus, SharedTaskList
from .file_locks import FileLockRegistry
from .messages import MessageBus, AgentMessage
from .spawner import AgentSpawner, WorkerResult
from .decomposer import TaskPlan, TaskDecomposer
from .lead import LeadAgent

__all__ = [
    "Task", "TaskStatus", "SharedTaskList",
    "FileLockRegistry",
    "MessageBus", "AgentMessage",
    "AgentSpawner", "WorkerResult",
    "TaskPlan", "TaskDecomposer",
    "LeadAgent",
]
