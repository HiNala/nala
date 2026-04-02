"""Safe, subprocess-based git operations for repo awareness.

All functions return plain strings or dicts — never raise on missing git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(args: list[str], cwd: Path, timeout: int = 5) -> str | None:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def is_git_repo(root: Path) -> bool:
    return _run(["git", "rev-parse", "--is-inside-work-tree"], root) == "true"


def current_branch(root: Path) -> str | None:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)


def tracking_status(root: Path) -> dict:
    """Return ahead/behind counts relative to upstream."""
    raw = _run(["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"], root)
    if not raw:
        return {"ahead": 0, "behind": 0, "tracking": False}
    parts = raw.split()
    if len(parts) == 2:
        return {"ahead": int(parts[0]), "behind": int(parts[1]), "tracking": True}
    return {"ahead": 0, "behind": 0, "tracking": False}


def uncommitted_summary(root: Path) -> dict:
    """Return counts of staged, modified, and untracked files."""
    raw = _run(["git", "status", "--porcelain"], root)
    if raw is None:
        return {"staged": 0, "modified": 0, "untracked": 0, "total": 0}
    staged = modified = untracked = 0
    for line in raw.splitlines():
        if len(line) < 2:
            continue
        idx, wt = line[0], line[1]
        if idx == "?" and wt == "?":
            untracked += 1
        elif idx != " " and idx != "?":
            staged += 1
        elif wt != " ":
            modified += 1
    total = staged + modified + untracked
    return {"staged": staged, "modified": modified, "untracked": untracked, "total": total}


def recent_commits(root: Path, count: int = 5) -> list[dict]:
    """Return recent commits as [{hash, subject, author, relative_date}]."""
    fmt = "%H%x00%s%x00%an%x00%ar"
    raw = _run(["git", "log", f"--max-count={count}", f"--pretty=format:{fmt}"], root)
    if not raw:
        return []
    commits = []
    for line in raw.splitlines():
        parts = line.split("\x00")
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0][:8],
                "subject": parts[1],
                "author": parts[2],
                "when": parts[3],
            })
    return commits


def diff_stat(root: Path, staged: bool = False) -> str | None:
    """Return diff --stat output."""
    args = ["git", "diff", "--stat"]
    if staged:
        args.append("--staged")
    return _run(args, root)


def diff_summary(root: Path) -> str:
    """Human-readable summary of all uncommitted changes."""
    lines: list[str] = []
    uc = uncommitted_summary(root)
    if uc["total"] == 0:
        return "Working tree is clean."

    parts = []
    if uc["staged"]:
        parts.append(f"{uc['staged']} staged")
    if uc["modified"]:
        parts.append(f"{uc['modified']} modified")
    if uc["untracked"]:
        parts.append(f"{uc['untracked']} untracked")
    lines.append(f"Uncommitted changes: {', '.join(parts)}")

    stat = diff_stat(root)
    if stat:
        lines.append("")
        lines.append("Unstaged changes:")
        lines.append(stat)

    staged_stat = diff_stat(root, staged=True)
    if staged_stat:
        lines.append("")
        lines.append("Staged changes:")
        lines.append(staged_stat)

    return "\n".join(lines)


def branch_info(root: Path) -> str:
    """Human-readable branch + tracking summary."""
    branch = current_branch(root) or "detached HEAD"
    lines = [f"Branch: {branch}"]
    ts = tracking_status(root)
    if ts["tracking"]:
        if ts["ahead"] or ts["behind"]:
            parts = []
            if ts["ahead"]:
                parts.append(f"{ts['ahead']} ahead")
            if ts["behind"]:
                parts.append(f"{ts['behind']} behind")
            lines.append(f"  {', '.join(parts)} of upstream")
        else:
            lines.append("  Up to date with upstream")
    else:
        lines.append("  No upstream tracking branch")

    commits = recent_commits(root, count=5)
    if commits:
        lines.append("")
        lines.append("Recent commits:")
        for c in commits:
            lines.append(f"  {c['hash']}  {c['subject']}  ({c['when']})")

    return "\n".join(lines)


def full_status(root: Path) -> str:
    """Combined git status overview."""
    if not is_git_repo(root):
        return "Not a git repository."

    lines = [branch_info(root)]
    lines.append("")
    lines.append(diff_summary(root))
    return "\n".join(lines)
