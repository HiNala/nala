"""Write settings to `.nala/settings.toml`.

Uses manual TOML serialization to produce clean, commented output
without requiring a third-party TOML writer library.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .schema import NalaSettings

log = logging.getLogger("nala.settings.writer")


class SettingsWriter:
    """Write NalaSettings to a TOML file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def write(self, settings: NalaSettings) -> Path:
        """Serialize and write settings to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = _serialize_toml(settings)
        self._path.write_text(content, encoding="utf-8")
        log.info("Settings written to %s", self._path)
        return self._path

    def set_value(self, dotted_key: str, value: str, settings: NalaSettings) -> str:
        """Set a single value by dotted key path and persist.

        Returns a status message.
        """
        parts = dotted_key.split(".")
        obj = settings
        for part in parts[:-1]:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return f"Unknown setting: {dotted_key}"

        final_key = parts[-1]
        if not hasattr(obj, final_key):
            return f"Unknown setting: {dotted_key}"

        current = getattr(obj, final_key)
        if isinstance(current, bool):
            coerced = value.lower() in ("true", "1", "yes")
            setattr(obj, final_key, coerced)
        elif isinstance(current, int):
            try:
                setattr(obj, final_key, int(value))
            except ValueError:
                return f"Invalid integer value: {value}"
        else:
            setattr(obj, final_key, value)

        self.write(settings)
        return f"Set `{dotted_key}` = `{value}`"


def _serialize_toml(settings: NalaSettings) -> str:
    """Produce a clean TOML string from settings."""
    lines: list[str] = [
        "# Nala settings — edit here or use `/settings set <key> <value>`",
        "# Environment variables (.env) take precedence over these values.",
        "",
    ]

    lines.append("[keys]")
    if settings.keys.anthropic_api_key:
        lines.append(f'anthropic_api_key = "{settings.keys.anthropic_api_key}"')
    else:
        lines.append("# anthropic_api_key = \"\"")
    if settings.keys.openai_api_key:
        lines.append(f'openai_api_key = "{settings.keys.openai_api_key}"')
    else:
        lines.append("# openai_api_key = \"\"")
    if settings.keys.google_api_key:
        lines.append(f'google_api_key = "{settings.keys.google_api_key}"')
    else:
        lines.append("# google_api_key = \"\"")
    if settings.keys.ollama_base_url != "http://localhost:11434":
        lines.append(f'ollama_base_url = "{settings.keys.ollama_base_url}"')

    lines.append("")
    lines.append("[models]")
    lines.append(f'default_provider = "{settings.models.default_provider}"')
    lines.append(f'default_model = "{settings.models.default_model}"')

    lines.append("")
    lines.append("[models.routing]")
    routing = settings.models.routing
    for task in ("plan", "code", "explore", "research", "design", "review", "summarize"):
        val = getattr(routing, task, "")
        if val:
            lines.append(f'{task} = "{val}"')
        else:
            lines.append(f"# {task} = \"\"")

    lines.append("")
    lines.append("[agent]")
    lines.append(f'autonomy = "{settings.agent.autonomy}"')
    lines.append(f"max_workers = {settings.agent.max_workers}")

    lines.append("")
    lines.append("[agent.git]")
    lines.append(f"auto_branch = {_bool(settings.agent.git.auto_branch)}")
    lines.append(f"auto_commit = {_bool(settings.agent.git.auto_commit)}")
    lines.append(f'branch_prefix = "{settings.agent.git.branch_prefix}"')

    lines.append("")
    lines.append("[agent.verification]")
    lines.append(f"auto_verify = {_bool(settings.agent.verification.auto_verify)}")
    lines.append(f"verify_timeout = {settings.agent.verification.verify_timeout}")

    lines.append("")
    lines.append("[display]")
    lines.append(f'theme = "{settings.display.theme}"')
    lines.append(f"show_startup_hints = {_bool(settings.display.show_startup_hints)}")
    lines.append("")

    return "\n".join(lines)


def _bool(val: bool) -> str:
    return "true" if val else "false"
