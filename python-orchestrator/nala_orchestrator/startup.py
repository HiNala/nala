"""Proactive startup intelligence — repo detection and suggested actions.

Called once after the IPC bridge sends ``ready``.  Returns a structured
dict that the Rust TUI renders as the first thing the user sees.
"""

from __future__ import annotations

from pathlib import Path

from . import git_ops

# ── Project type detection ──────────────────────────────────────────────

_MARKERS: dict[str, list[str]] = {
    "rust": ["Cargo.toml"],
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
    "node": ["package.json"],
    "go": ["go.mod"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "dotnet": ["*.csproj", "*.sln"],
    "ruby": ["Gemfile"],
    "php": ["composer.json"],
}


def detect_project_types(root: Path) -> list[str]:
    """Return a list of detected project ecosystems (e.g. ['rust', 'python']).

    Checks the root directory and one level of subdirectories so that
    monorepos like ``rust-core/Cargo.toml`` are detected.
    """
    found: list[str] = []
    children = set()
    try:
        children = {e.name for e in root.iterdir()}
    except OSError:
        pass

    sub_children: set[str] = set()
    try:
        for entry in root.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                for sub in entry.iterdir():
                    sub_children.add(sub.name)
    except OSError:
        pass

    all_names = children | sub_children

    for lang, markers in _MARKERS.items():
        for m in markers:
            if "*" in m:
                if any(root.glob(m)) or any(root.glob(f"*/{m}")):
                    found.append(lang)
                    break
            elif m in all_names:
                found.append(lang)
                break
    return found


def detect_entry_points(root: Path, project_types: list[str]) -> list[str]:
    """Return likely entry-point files for the detected project types."""
    candidates: list[str] = []
    checks: list[str] = []
    if "rust" in project_types:
        checks += ["src/main.rs", "src/lib.rs"]
    if "python" in project_types:
        checks += ["main.py", "app.py", "manage.py", "cli.py"]
    if "node" in project_types:
        checks += ["src/index.ts", "src/index.js", "index.js", "server.js", "app.js"]
    if "go" in project_types:
        checks += ["main.go", "cmd/main.go"]

    for c in checks:
        if (root / c).exists():
            candidates.append(c)
    return candidates[:5]


# ── Suggestion engine ───────────────────────────────────────────────────

def _suggest_actions(
    root: Path,
    project_types: list[str],
    git_available: bool,
    uncommitted: int,
    has_sessions: bool,
    file_count: int,
    symbol_count: int,
) -> list[str]:
    """Generate 3–5 contextual suggestions based on repo state."""
    suggestions: list[str] = []

    if file_count > 0 and symbol_count > 0:
        suggestions.append("/agent hotspot — find high-value improvement targets")

    if git_available and uncommitted > 0:
        plural = "s" if uncommitted != 1 else ""
        suggestions.append(
            f"/agent review — review {uncommitted} uncommitted change{plural}",
        )

    if has_sessions:
        suggestions.append("/session list — resume a previous session")

    if "rust" in project_types:
        suggestions.append("Ask: \"find the most complex functions in this codebase\"")
    elif "python" in project_types:
        suggestions.append("Ask: \"explain the architecture of this project\"")
    elif "node" in project_types:
        suggestions.append("Ask: \"what are the main API endpoints?\"")
    else:
        suggestions.append("Ask a question about this codebase")

    if len(suggestions) < 3:
        suggestions.append("/help — see all available commands")

    return suggestions[:5]


# ── Main entry point ────────────────────────────────────────────────────

def gather_startup_intelligence(
    root: Path,
    file_count: int = 0,
    symbol_count: int = 0,
) -> dict:
    """Gather all proactive startup information.

    Returns a dict ready to be serialized as a JSON IPC message.
    """
    project_types = detect_project_types(root)
    entry_points = detect_entry_points(root, project_types)

    git_available = git_ops.is_git_repo(root)
    branch = git_ops.current_branch(root) if git_available else None
    tracking = git_ops.tracking_status(root) if git_available else {}
    uncommitted = git_ops.uncommitted_summary(root) if git_available else {}
    uncommitted_total = uncommitted.get("total", 0)

    sessions_dir = root / ".nala" / "sessions"
    has_sessions = (
        sessions_dir.exists() and any(sessions_dir.iterdir())
        if sessions_dir.exists()
        else False
    )

    suggestions = _suggest_actions(
        root, project_types, git_available,
        uncommitted_total, has_sessions, file_count, symbol_count,
    )

    return {
        "type": "startup_intelligence",
        "project_types": project_types,
        "entry_points": entry_points,
        "git": {
            "available": git_available,
            "branch": branch,
            "ahead": tracking.get("ahead", 0),
            "behind": tracking.get("behind", 0),
            "tracking": tracking.get("tracking", False),
            "uncommitted": uncommitted_total,
            "staged": uncommitted.get("staged", 0),
            "modified": uncommitted.get("modified", 0),
            "untracked": uncommitted.get("untracked", 0),
        },
        "has_sessions": has_sessions,
        "suggestions": suggestions,
    }
