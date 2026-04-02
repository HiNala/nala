"""Git review flow — surfaces review-friendly summaries for /agent workflows.

Combines git_ops primitives with risk annotations to produce review
artifacts suitable for terminal display and LLM consumption.
"""

from __future__ import annotations

from pathlib import Path

from . import git_ops


def current_review(root: Path) -> str:
    """Comprehensive review of all uncommitted work."""
    if not git_ops.is_git_repo(root):
        return "Not a git repository."

    parts: list[str] = []
    branch = git_ops.current_branch(root) or "detached"
    ts = git_ops.tracking_status(root)
    parts.append(f"## Review — `{branch}`")

    if ts["tracking"]:
        ahead, behind = ts["ahead"], ts["behind"]
        if ahead or behind:
            parts.append(
                f"Upstream: {ahead} ahead, {behind} behind"
            )

    uc = git_ops.uncommitted_summary(root)
    if uc["total"] == 0:
        parts.append("\nWorking tree is clean — nothing to review.")
        return "\n".join(parts)

    parts.append(
        f"\n**Uncommitted:** {uc['staged']} staged, "
        f"{uc['modified']} modified, {uc['untracked']} untracked"
    )

    staged_stat = git_ops.diff_stat(root, staged=True)
    if staged_stat:
        parts.append(f"\n### Staged changes\n```\n{staged_stat}\n```")

    unstaged_stat = git_ops.diff_stat(root, staged=False)
    if unstaged_stat:
        parts.append(f"\n### Unstaged changes\n```\n{unstaged_stat}\n```")

    commits = git_ops.recent_commits(root, count=5)
    if commits:
        parts.append("\n### Recent commits")
        for c in commits:
            parts.append(f"  `{c['hash']}` {c['subject']} ({c['when']})")

    return "\n".join(parts)


def branch_review(root: Path, base: str = "main", head: str = "HEAD") -> str:
    """Review changes between two branches."""
    if not git_ops.is_git_repo(root):
        return "Not a git repository."

    parts: list[str] = [f"## Branch Review — `{base}` → `{head}`"]
    comparison = git_ops.branch_compare(root, base, head)
    parts.append(comparison)
    return "\n".join(parts)


def changed_files_list(root: Path, staged_only: bool = False) -> list[str]:
    """Return list of changed file paths."""
    if not git_ops.is_git_repo(root):
        return []
    args = ["git", "diff", "--name-only"]
    if staged_only:
        args.append("--staged")
    raw = git_ops._run(args, root)
    if not raw:
        return []
    return [f.strip() for f in raw.splitlines() if f.strip()]


def scm_overview(root: Path) -> str:
    """Full SCM overview for /agent scm."""
    if not git_ops.is_git_repo(root):
        return "Not a git repository."

    parts: list[str] = ["## SCM Overview"]

    parts.append(f"\n### Branch\n{git_ops.branch_info(root)}")
    parts.append(f"\n### Working Tree\n{git_ops.diff_summary(root)}")

    wt = git_ops.worktree_status(root)
    if "No additional" not in wt:
        parts.append(f"\n### Worktrees\n{wt}")

    return "\n".join(parts)
