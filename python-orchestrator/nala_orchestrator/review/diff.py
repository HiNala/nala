from __future__ import annotations

import subprocess
from pathlib import Path


_GIT_TIMEOUT_SECS = 15


def get_changed_files(project_root: str) -> list[str]:
    """Retrieve list of modified files via git diff."""
    root = Path(project_root)
    try:
        # Check both staged and unstaged
        unstaged = subprocess.check_output(
            ["git", "diff", "--name-only"],
            cwd=str(root),
            text=True,
            timeout=_GIT_TIMEOUT_SECS,
        ).splitlines()

        staged = subprocess.check_output(
            ["git", "diff", "--staged", "--name-only"],
            cwd=str(root),
            text=True,
            timeout=_GIT_TIMEOUT_SECS,
        ).splitlines()

        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(root),
            text=True,
            timeout=_GIT_TIMEOUT_SECS,
        ).splitlines()

        all_changed = set(unstaged + staged + untracked)
        return [str(root / f) for f in all_changed if f.strip() and (root / f).is_file()]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return []
