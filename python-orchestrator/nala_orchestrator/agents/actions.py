"""
Action types for inline agent modifications.

Actions are proposed by the LLM, previewed for the user, and only applied
after explicit confirmation. The XML format embedded in LLM responses is:

  <action type="edit" file="src/auth.py">
  <old>
  ...exact text to replace...
  </old>
  <new>
  ...replacement text...
  </new>
  <description>Human-readable summary</description>
  </action>
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Union


@dataclass
class EditAction:
    """Replace exact text in an existing file."""

    file_path: str
    old_content: str
    new_content: str
    description: str
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: str = "edit"


@dataclass
class CreateAction:
    """Write a new file. Refuses to overwrite existing files."""

    file_path: str
    content: str
    description: str
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: str = "create"


@dataclass
class DeleteAction:
    """Delete an existing file. Always requires explicit confirmation."""

    file_path: str
    description: str
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: str = "delete"


@dataclass
class ShellAction:
    """Run a shell command sandboxed to the project directory."""

    command: str
    description: str
    working_dir: str = "."
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: str = "shell"


# Union type for type-checking convenience
Action = Union[EditAction, CreateAction, DeleteAction, ShellAction]


@dataclass
class ActionResult:
    """Result of applying an action."""

    action_id: str
    success: bool
    message: str = ""
    output: str = ""
