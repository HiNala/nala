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


# ── Branch comparison ──────────────────────────────────────────────────

def branch_compare(root: Path, base: str, head: str = "HEAD") -> str:
    """Compare two branches/revisions and return a human-readable summary."""
    if not is_git_repo(root):
        return "Not a git repository."

    count_raw = _run(
        ["git", "rev-list", "--count", f"{base}..{head}"], root,
    )
    commit_count = int(count_raw) if count_raw and count_raw.isdigit() else 0

    stat = _run(["git", "diff", "--stat", f"{base}...{head}"], root)
    log_raw = _run(
        ["git", "log", "--oneline", "--max-count=15", f"{base}..{head}"],
        root,
    )

    lines = [f"**Comparing** `{base}` → `{head}` ({commit_count} commits)"]
    if log_raw:
        lines.append("\n**Commits:**")
        for log_line in log_raw.splitlines()[:15]:
            lines.append(f"  {log_line}")
    if stat:
        lines.append(f"\n**Files changed:**\n{stat}")
    return "\n".join(lines)


def commit_diff(root: Path, rev_a: str, rev_b: str = "") -> str:
    """Return diff between two revisions, or show a single commit's diff."""
    if not is_git_repo(root):
        return "Not a git repository."
    if rev_b:
        raw = _run(["git", "diff", "--stat", rev_a, rev_b], root)
        patch = _run(["git", "diff", "--shortstat", rev_a, rev_b], root)
    else:
        raw = _run(["git", "show", "--stat", rev_a], root)
        patch = _run(["git", "show", "--shortstat", rev_a], root)
    lines = []
    if raw:
        lines.append(raw)
    if patch:
        lines.append(f"\n{patch}")
    return "\n".join(lines) if lines else "No diff available."


def blame_summary(root: Path, file_path: str, start: int = 1, end: int = 0) -> str:
    """Return git blame summary for a file (or line range)."""
    if not is_git_repo(root):
        return "Not a git repository."
    args = ["git", "blame", "--line-porcelain"]
    if end > 0:
        args.extend([f"-L{start},{end}"])
    args.append(file_path)
    raw = _run(args, root, timeout=10)
    if not raw:
        return f"No blame data for {file_path}"

    authors: dict[str, int] = {}
    for line in raw.splitlines():
        if line.startswith("author "):
            author = line[7:].strip()
            authors[author] = authors.get(author, 0) + 1

    total = sum(authors.values())
    sorted_authors = sorted(authors.items(), key=lambda x: -x[1])
    lines = [f"**Blame for `{file_path}`** ({total} lines)"]
    for author, count in sorted_authors[:10]:
        pct = count * 100 // total if total else 0
        lines.append(f"  {author}: {count} lines ({pct}%)")
    return "\n".join(lines)


# ── Worktree support ──────────────────────────────────────────────────

def list_worktrees(root: Path) -> list[dict]:
    """Return a list of active git worktrees."""
    raw = _run(["git", "worktree", "list", "--porcelain"], root)
    if not raw:
        return []
    trees: list[dict] = []
    current: dict = {}
    for line in raw.splitlines():
        if line.startswith("worktree "):
            if current:
                trees.append(current)
            current = {"path": line[9:].strip()}
        elif line.startswith("HEAD "):
            current["head"] = line[5:].strip()[:8]
        elif line.startswith("branch "):
            current["branch"] = line[7:].strip().replace("refs/heads/", "")
        elif line == "bare":
            current["bare"] = True
    if current:
        trees.append(current)
    return trees


def create_worktree(root: Path, label: str, branch: str = "") -> str | None:
    """Create a new git worktree. Returns the path or None on failure."""
    wt_dir = root / ".nala" / "worktrees" / label
    wt_dir.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "worktree", "add"]
    if branch:
        args.extend(["-b", branch])
    else:
        args.extend(["-b", f"nala/{label}"])
    args.append(str(wt_dir))
    result = _run(args, root, timeout=15)
    if result is not None or wt_dir.exists():
        return str(wt_dir)
    return None


def cleanup_worktree(root: Path, label: str) -> bool:
    """Remove a worktree and its branch."""
    wt_dir = root / ".nala" / "worktrees" / label
    result = _run(["git", "worktree", "remove", str(wt_dir), "--force"], root)
    branch = f"nala/{label}"
    _run(["git", "branch", "-D", branch], root)
    return result is not None or not wt_dir.exists()


# ── Agent orchestration git operations ────────────────────────────────


def create_agent_branch(root: Path, run_id: str) -> str | None:
    """Create a feature branch for an agent run. Returns branch name or None."""
    if not is_git_repo(root):
        return None
    branch = f"nala/agent-{run_id}"
    existing = current_branch(root)
    if existing == branch:
        return branch
    result = _run(["git", "checkout", "-b", branch], root, timeout=10)
    if result is not None:
        return branch
    check = _run(["git", "checkout", branch], root, timeout=10)
    if check is not None:
        return branch
    return None


def commit_milestone(root: Path, message: str, files: list[str] | None = None) -> str | None:
    """Stage and commit. Returns the short hash or None on failure."""
    if not is_git_repo(root):
        return None
    if files:
        for f in files:
            _run(["git", "add", f], root)
    else:
        _run(["git", "add", "-A"], root)
    uc = uncommitted_summary(root)
    if uc["staged"] == 0 and uc["total"] == 0:
        return None
    result = _run(["git", "commit", "-m", message], root, timeout=30)
    if result is None:
        return None
    short = _run(["git", "rev-parse", "--short", "HEAD"], root)
    return short


def switch_back_to_branch(root: Path, branch: str) -> bool:
    """Switch back to a branch (e.g., after agent run on feature branch)."""
    if not is_git_repo(root):
        return False
    return _run(["git", "checkout", branch], root, timeout=10) is not None


def get_run_diff_summary(root: Path, base_branch: str = "main") -> str:
    """Summarise changes between the current branch and base."""
    if not is_git_repo(root):
        return "Not a git repository."
    head = current_branch(root) or "HEAD"
    if head == base_branch:
        return "Agent branch is the same as base — no diff."
    return branch_compare(root, base_branch, head)


def create_worktree_for_worker(root: Path, worker_id: str) -> str | None:
    """Create a worktree scoped to a worker. Returns path or None."""
    return create_worktree(root, f"worker-{worker_id}")


def cleanup_worker_worktree(root: Path, worker_id: str) -> bool:
    """Clean up a worker's worktree."""
    return cleanup_worktree(root, f"worker-{worker_id}")


def worktree_status(root: Path) -> str:
    """Human-readable worktree summary."""
    trees = list_worktrees(root)
    if len(trees) <= 1:
        return "No additional worktrees."
    lines = [f"**Worktrees** ({len(trees)} total)"]
    for t in trees:
        branch = t.get("branch", "detached")
        head = t.get("head", "")
        lines.append(f"  {branch} @ {head} → {t['path']}")
    return "\n".join(lines)
