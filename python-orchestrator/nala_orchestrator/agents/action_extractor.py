"""
ActionExtractor — parse XML action blocks from LLM response text.

The LLM is prompted to embed action blocks using this format:

  <action type="edit" file="src/auth.py">
  <old>
  exact text to replace
  </old>
  <new>
  replacement text
  </new>
  <description>Human summary of the change</description>
  </action>

  <action type="create" file="src/new_module.py">
  <new>
  full file content
  </new>
  <description>Create new helper module</description>
  </action>

  <action type="shell">
  <command>pip install bcrypt</command>
  <description>Install bcrypt dependency</description>
  </action>

  <action type="delete" file="src/old_module.py">
  <description>Remove obsolete module</description>
  </action>
"""

from __future__ import annotations

import re
from typing import Optional

from .actions import (
    Action,
    CreateAction,
    DeleteAction,
    EditAction,
    ShellAction,
)

# Match a full <action>…</action> block (non-greedy, DOTALL)
_ACTION_BLOCK = re.compile(
    r'<action\b([^>]*)>(.*?)</action>',
    re.DOTALL | re.IGNORECASE,
)
# Extract named attributes from the opening tag
_ATTR_TYPE = re.compile(r'\btype=["\']([^"\']+)["\']', re.IGNORECASE)
_ATTR_FILE = re.compile(r'\bfile=["\']([^"\']+)["\']', re.IGNORECASE)
# Extract inner XML elements
_ELEM_OLD = re.compile(r'<old>(.*?)</old>', re.DOTALL | re.IGNORECASE)
_ELEM_NEW = re.compile(r'<new>(.*?)</new>', re.DOTALL | re.IGNORECASE)
_ELEM_DESC = re.compile(r'<description>(.*?)</description>', re.DOTALL | re.IGNORECASE)
_ELEM_CMD = re.compile(r'<command>(.*?)</command>', re.DOTALL | re.IGNORECASE)


def _strip(text: Optional[str]) -> str:
    return text.strip() if text else ""


class ActionExtractor:
    """Parses action XML blocks from an LLM response."""

    def extract(self, text: str) -> tuple[str, list[Action]]:
        """
        Return ``(cleaned_text, actions)``.

        ``cleaned_text`` has all action blocks removed so only the prose
        explanation remains. ``actions`` is the ordered list of parsed actions.
        """
        actions: list[Action] = []
        positions: list[tuple[int, int]] = []  # (start, end) of each block

        for m in _ACTION_BLOCK.finditer(text):
            positions.append((m.start(), m.end()))
            attrs = m.group(1)
            body = m.group(2)

            action_type = _strip(_ATTR_TYPE.search(attrs) and _ATTR_TYPE.search(attrs).group(1))  # type: ignore[union-attr]
            file_path = _strip(_ATTR_FILE.search(attrs) and _ATTR_FILE.search(attrs).group(1))  # type: ignore[union-attr]

            desc_m = _ELEM_DESC.search(body)
            description = _strip(desc_m.group(1) if desc_m else "")

            action: Optional[Action] = None

            if action_type == "edit":
                old_m = _ELEM_OLD.search(body)
                new_m = _ELEM_NEW.search(body)
                if old_m and new_m and file_path:
                    action = EditAction(
                        file_path=file_path,
                        old_content=_strip(old_m.group(1)),
                        new_content=_strip(new_m.group(1)),
                        description=description,
                    )

            elif action_type == "create":
                new_m = _ELEM_NEW.search(body)
                content = _strip(new_m.group(1)) if new_m else _strip(body)
                if file_path:
                    action = CreateAction(
                        file_path=file_path,
                        content=content,
                        description=description,
                    )

            elif action_type == "delete":
                if file_path:
                    action = DeleteAction(
                        file_path=file_path,
                        description=description,
                    )

            elif action_type == "shell":
                cmd_m = _ELEM_CMD.search(body)
                command = _strip(cmd_m.group(1)) if cmd_m else _strip(body)
                if command:
                    action = ShellAction(
                        command=command,
                        description=description,
                    )

            if action is not None:
                actions.append(action)

        # Build cleaned text by excising action blocks
        if not positions:
            return text, actions

        parts: list[str] = []
        prev = 0
        for start, end in positions:
            parts.append(text[prev:start])
            prev = end
        parts.append(text[prev:])
        cleaned = re.sub(r'\n{3,}', '\n\n', "".join(parts)).strip()

        return cleaned, actions


# Module-level singleton for convenience
_extractor = ActionExtractor()


def extract_actions(text: str) -> tuple[str, list[Action]]:
    """Convenience wrapper around ``ActionExtractor.extract``."""
    return _extractor.extract(text)
