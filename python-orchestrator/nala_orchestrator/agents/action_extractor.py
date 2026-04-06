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

import logging
import re

from .actions import (
    Action,
    CreateAction,
    DeleteAction,
    EditAction,
    ShellAction,
)

log = logging.getLogger("nala.action_extractor")

# Match a full <action>…</action> block (non-greedy, DOTALL)
_ACTION_BLOCK = re.compile(
    r'<action\b([^>]*)>(.*?)</action>',
    re.DOTALL | re.IGNORECASE,
)
# Extract named attributes from the opening tag
_ATTR_TYPE = re.compile(r'\btype=["\']([^"\']+)["\']', re.IGNORECASE)
_ATTR_FILE = re.compile(r'\bfile=["\']([^"\']+)["\']', re.IGNORECASE)
# Extract inner XML elements
_ELEM_OLD  = re.compile(r'<old>(.*?)</old>',               re.DOTALL | re.IGNORECASE)
_ELEM_NEW  = re.compile(r'<new>(.*?)</new>',               re.DOTALL | re.IGNORECASE)
_ELEM_DESC = re.compile(r'<description>(.*?)</description>', re.DOTALL | re.IGNORECASE)
_ELEM_CMD  = re.compile(r'<command>(.*?)</command>',        re.DOTALL | re.IGNORECASE)


def _strip(text: str | None) -> str:
    return text.strip() if text else ""


def _match_group(pattern: re.Pattern, text: str, group: int = 1) -> str:
    """Safe single-call match — avoids calling .search() twice."""
    m = pattern.search(text)
    return m.group(group) if m else ""


class ActionExtractor:
    """Parses action XML blocks from an LLM response."""

    def extract(self, text: str) -> tuple[str, list[Action]]:
        """
        Return ``(cleaned_text, actions)``.

        ``cleaned_text`` has all action blocks removed so only the prose
        explanation remains.  ``actions`` is the ordered list of parsed
        actions.  Parse warnings for skipped blocks are logged at WARNING
        level so the user can see them in debug output.
        """
        actions: list[Action] = []
        positions: list[tuple[int, int]] = []  # (start, end) of each block

        for block_num, m in enumerate(_ACTION_BLOCK.finditer(text), start=1):
            positions.append((m.start(), m.end()))
            attrs = m.group(1)
            body  = m.group(2)

            action_type = _strip(_match_group(_ATTR_TYPE, attrs))
            file_path   = _strip(_match_group(_ATTR_FILE, attrs))
            description = _strip(_match_group(_ELEM_DESC, body))

            action: Action | None = None
            skip_reason: str = ""

            try:
                if action_type == "edit":
                    old_text = _strip(_match_group(_ELEM_OLD, body))
                    new_text = _strip(_match_group(_ELEM_NEW, body))
                    if not file_path:
                        skip_reason = "missing file= attribute"
                    elif not old_text:
                        skip_reason = "missing <old> element"
                    elif not new_text and new_text != old_text:
                        # Allow empty new_text only if explicitly present
                        new_m = _ELEM_NEW.search(body)
                        if new_m is None:
                            skip_reason = "missing <new> element"
                        else:
                            action = EditAction(
                                file_path=file_path,
                                old_content=old_text,
                                new_content=new_text,
                                description=description,
                            )
                    else:
                        action = EditAction(
                            file_path=file_path,
                            old_content=old_text,
                            new_content=new_text,
                            description=description,
                        )

                elif action_type == "create":
                    new_m = _ELEM_NEW.search(body)
                    content = _strip(new_m.group(1)) if new_m else _strip(body)
                    if not file_path:
                        skip_reason = "missing file= attribute"
                    elif not content:
                        skip_reason = "empty content"
                    else:
                        action = CreateAction(
                            file_path=file_path,
                            content=content,
                            description=description,
                        )

                elif action_type == "delete":
                    if not file_path:
                        skip_reason = "missing file= attribute"
                    else:
                        action = DeleteAction(
                            file_path=file_path,
                            description=description,
                        )

                elif action_type == "shell":
                    command = _strip(_match_group(_ELEM_CMD, body)) or _strip(body)
                    if not command:
                        skip_reason = "missing <command> element or empty body"
                    else:
                        action = ShellAction(
                            command=command,
                            description=description,
                        )

                elif action_type:
                    skip_reason = f"unknown action type: {action_type!r}"

                else:
                    skip_reason = "missing type= attribute"

            except Exception as exc:
                skip_reason = f"parse error: {exc}"
                log.exception("Unexpected error parsing action block #%d", block_num)

            if action is not None:
                actions.append(action)
            elif skip_reason:
                log.warning(
                    "Action block #%d skipped (%s). "
                    "Attributes: type=%r file=%r. "
                    "Check the LLM output for malformed XML.",
                    block_num, skip_reason, action_type, file_path,
                )

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
