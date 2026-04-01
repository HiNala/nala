"""
ActionExecutor — safely apply agent-proposed code actions.

Safety guarantees (non-negotiable):
- EditAction: replaces exact string only; fails if old_content not found
- CreateAction: refuses to overwrite existing files
- DeleteAction: always requires prior user confirmation (enforced by TUI)
- ShellAction: working dir must be inside project root; 30-second timeout
- Session limit of 50 applied actions prevents runaway loops
"""

from __future__ import annotations

import difflib
import subprocess
from pathlib import Path

from .actions import (
    Action,
    ActionResult,
    CreateAction,
    DeleteAction,
    EditAction,
    ShellAction,
)

_MAX_DIFF_LINES = 40
_MAX_ACTIONS = 50
_SHELL_TIMEOUT = 30  # seconds


class ActionExecutor:
    """Applies confirmed actions to the file system."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()
        self._applied: int = 0

    # ── Public API ─────────────────────────────────────────────────────────

    def preview(self, action: Action) -> str:
        """Return a human-readable diff/preview string for TUI display."""
        if isinstance(action, EditAction):
            return self._diff_edit(action)
        if isinstance(action, CreateAction):
            return self._preview_create(action)
        if isinstance(action, DeleteAction):
            return f"--- DELETE: {action.file_path}"
        if isinstance(action, ShellAction):
            wd = action.working_dir if action.working_dir != "." else "(project root)"
            return f"$ {action.command}\n  cwd: {wd}"
        return "(unknown action type)"

    def apply(self, action: Action) -> ActionResult:
        """Apply the action. Returns an ActionResult with success/failure."""
        if self._applied >= _MAX_ACTIONS:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                message=f"Session action limit ({_MAX_ACTIONS}) reached.",
            )
        if isinstance(action, EditAction):
            result = self._apply_edit(action)
        elif isinstance(action, CreateAction):
            result = self._apply_create(action)
        elif isinstance(action, DeleteAction):
            result = self._apply_delete(action)
        elif isinstance(action, ShellAction):
            result = self._apply_shell(action)
        else:
            result = ActionResult(
                action_id=action.action_id,
                success=False,
                message="Unknown action type.",
            )
        if result.success:
            self._applied += 1
        return result

    # ── Preview helpers ────────────────────────────────────────────────────

    def _diff_edit(self, action: EditAction) -> str:
        old_lines = action.old_content.splitlines(keepends=True)
        new_lines = action.new_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{action.file_path}",
            tofile=f"b/{action.file_path}",
            lineterm="",
        ))
        if len(diff) > _MAX_DIFF_LINES:
            diff = diff[:_MAX_DIFF_LINES]
            diff.append(f"... ({len(diff)} total lines truncated)")
        return "\n".join(diff) or "(no diff — old and new content are identical)"

    def _preview_create(self, action: CreateAction) -> str:
        lines = [f"+++ {action.file_path} (new file)"]
        for line in action.content.splitlines()[:_MAX_DIFF_LINES]:
            lines.append(f"+ {line}")
        extra = action.content.count("\n") - _MAX_DIFF_LINES
        if extra > 0:
            lines.append(f"... {extra} more lines")
        return "\n".join(lines)

    # ── Apply helpers ──────────────────────────────────────────────────────

    def _resolve(self, file_path: str) -> Path:
        p = Path(file_path)
        if not p.is_absolute():
            p = self.root / p
        return p.resolve()

    def _apply_edit(self, action: EditAction) -> ActionResult:
        path = self._resolve(action.file_path)
        if not path.exists():
            return ActionResult(action.action_id, False, f"File not found: {action.file_path}")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return ActionResult(action.action_id, False, str(exc))
        if action.old_content not in text:
            return ActionResult(
                action.action_id, False,
                "old_content not found in file — the file may have changed."
            )
        new_text = text.replace(action.old_content, action.new_content, 1)
        try:
            path.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            return ActionResult(action.action_id, False, str(exc))
        return ActionResult(action.action_id, True, f"Edited {action.file_path}")

    def _apply_create(self, action: CreateAction) -> ActionResult:
        path = self._resolve(action.file_path)
        if path.exists():
            return ActionResult(
                action.action_id, False,
                f"File already exists: {action.file_path} — will not overwrite."
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(action.content, encoding="utf-8")
        except OSError as exc:
            return ActionResult(action.action_id, False, str(exc))
        return ActionResult(action.action_id, True, f"Created {action.file_path}")

    def _apply_delete(self, action: DeleteAction) -> ActionResult:
        path = self._resolve(action.file_path)
        if not path.exists():
            return ActionResult(action.action_id, False, f"File not found: {action.file_path}")
        try:
            path.unlink()
        except OSError as exc:
            return ActionResult(action.action_id, False, str(exc))
        return ActionResult(action.action_id, True, f"Deleted {action.file_path}")

    def _apply_shell(self, action: ShellAction) -> ActionResult:
        # Resolve and sandbox working directory
        work_dir = (self.root / action.working_dir).resolve()
        try:
            work_dir.relative_to(self.root)
        except ValueError:
            return ActionResult(
                action.action_id, False,
                "Shell working dir is outside the project root — refused."
            )
        try:
            proc = subprocess.run(
                action.command,
                shell=True,  # noqa: S602
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=_SHELL_TIMEOUT,
            )
            output = (proc.stdout + proc.stderr).strip()
            success = proc.returncode == 0
            return ActionResult(
                action.action_id,
                success,
                f"Exit code {proc.returncode}",
                output,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                action.action_id, False,
                f"Command timed out after {_SHELL_TIMEOUT}s."
            )
        except Exception as exc:
            return ActionResult(action.action_id, False, str(exc))
