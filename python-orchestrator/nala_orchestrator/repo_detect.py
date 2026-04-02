"""Repo-aware command detection.

Detects project toolchains and maps them to correct build, test, lint,
and format commands so the agent can suggest accurate verification steps.
"""

from __future__ import annotations

from pathlib import Path


def detect_commands(root: Path) -> dict[str, str]:
    """Detect available project commands based on config files.

    Returns a dict like::

        {"test": "cargo test", "lint": "cargo clippy", "format": "cargo fmt"}
    """
    commands: dict[str, str] = {}

    if (root / "Cargo.toml").exists() or _has_in_subdirs(root, "Cargo.toml"):
        commands.setdefault("test", "cargo test")
        commands.setdefault("lint", "cargo clippy")
        commands.setdefault("format", "cargo fmt")
        commands.setdefault("build", "cargo build")

    if (root / "pyproject.toml").exists() or _has_in_subdirs(
        root, "pyproject.toml"
    ):
        if _file_contains(root, "pyproject.toml", "ruff"):
            commands.setdefault("lint", "ruff check .")
            commands.setdefault("format", "ruff format .")
        commands.setdefault("test", "pytest")

    if (root / "package.json").exists():
        commands.setdefault("test", "npm test")
        commands.setdefault("lint", "npm run lint")
        commands.setdefault("build", "npm run build")

    if (root / "go.mod").exists():
        commands.setdefault("test", "go test ./...")
        commands.setdefault("lint", "golangci-lint run")
        commands.setdefault("build", "go build ./...")

    if (root / "Makefile").exists():
        commands.setdefault("build", "make")
        commands.setdefault("test", "make test")

    return commands


def commands_summary(root: Path) -> str:
    """Return a human-readable summary of detected project commands."""
    cmds = detect_commands(root)
    if not cmds:
        return ""
    lines = ["Detected project commands:"]
    for role, cmd in sorted(cmds.items()):
        lines.append(f"  {role}: {cmd}")
    return "\n".join(lines)


def _has_in_subdirs(root: Path, filename: str) -> bool:
    """Check if filename exists in any immediate subdirectory."""
    try:
        for entry in root.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                if (entry / filename).exists():
                    return True
    except OSError:
        pass
    return False


def _file_contains(root: Path, filename: str, needle: str) -> bool:
    """Check if a file at root/filename contains a string."""
    path = root / filename
    if not path.exists():
        for entry in root.iterdir():
            if entry.is_dir() and (entry / filename).exists():
                path = entry / filename
                break
    try:
        return needle in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
