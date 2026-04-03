"""Load settings from `.nala/settings.toml` with fallbacks.

Priority (highest wins):
  1. Environment variables (always override everything)
  2. Project-level `.nala/settings.toml`
  3. Global `~/.nala/settings.toml`
  4. Built-in defaults
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path

from .schema import (
    AgentGitSettings,
    AgentSettings,
    AgentVerificationSettings,
    DisplaySettings,
    KeysSettings,
    ModelRoutingSettings,
    ModelsSettings,
    NalaSettings,
)

log = logging.getLogger("nala.settings.loader")

SETTINGS_FILENAME = "settings.toml"


class SettingsLoader:
    """Read and merge settings from multiple sources."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._root = project_root or Path.cwd()
        self._global_path = Path.home() / ".nala" / SETTINGS_FILENAME
        self._project_path = self._root / ".nala" / SETTINGS_FILENAME

    @property
    def project_path(self) -> Path:
        return self._project_path

    @property
    def global_path(self) -> Path:
        return self._global_path

    def load(self) -> NalaSettings:
        """Load and merge settings from all sources."""
        global_raw = self._read_toml(self._global_path)
        project_raw = self._read_toml(self._project_path)

        merged = _deep_merge(global_raw, project_raw)
        settings = _parse_settings(merged)
        _apply_env_overrides(settings)
        return settings

    def has_project_settings(self) -> bool:
        return self._project_path.exists()

    def has_global_settings(self) -> bool:
        return self._global_path.exists()

    def has_any_settings(self) -> bool:
        return self.has_project_settings() or self.has_global_settings()

    def _read_toml(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except Exception as exc:
            log.warning("Failed to read %s: %s", path, exc)
            return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override values win."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _parse_settings(raw: dict) -> NalaSettings:
    """Parse a raw TOML dict into typed settings objects."""
    keys_raw = raw.get("keys", {})
    keys = KeysSettings(
        anthropic_api_key=keys_raw.get("anthropic_api_key", ""),
        openai_api_key=keys_raw.get("openai_api_key", ""),
        google_api_key=keys_raw.get("google_api_key", ""),
        ollama_base_url=keys_raw.get("ollama_base_url", "http://localhost:11434"),
    )

    models_raw = raw.get("models", {})
    routing_raw = models_raw.get("routing", {})
    routing = ModelRoutingSettings(
        plan=routing_raw.get("plan", ""),
        code=routing_raw.get("code", ""),
        explore=routing_raw.get("explore", ""),
        research=routing_raw.get("research", ""),
        design=routing_raw.get("design", ""),
        review=routing_raw.get("review", ""),
        summarize=routing_raw.get("summarize", ""),
    )
    models = ModelsSettings(
        default_provider=models_raw.get("default_provider", ""),
        default_model=models_raw.get("default_model", ""),
        routing=routing,
    )

    agent_raw = raw.get("agent", {})
    git_raw = agent_raw.get("git", {})
    verify_raw = agent_raw.get("verification", {})
    agent = AgentSettings(
        autonomy=agent_raw.get("autonomy", "guided"),
        max_workers=agent_raw.get("max_workers", 3),
        git=AgentGitSettings(
            auto_branch=git_raw.get("auto_branch", True),
            auto_commit=git_raw.get("auto_commit", True),
            branch_prefix=git_raw.get("branch_prefix", "nala/agent-"),
        ),
        verification=AgentVerificationSettings(
            auto_verify=verify_raw.get("auto_verify", True),
            verify_timeout=verify_raw.get("verify_timeout", 120),
        ),
    )

    display_raw = raw.get("display", {})
    display = DisplaySettings(
        theme=display_raw.get("theme", "dark"),
        show_startup_hints=display_raw.get("show_startup_hints", True),
    )

    return NalaSettings(keys=keys, models=models, agent=agent, display=display)


def _apply_env_overrides(settings: NalaSettings) -> None:
    """Environment variables always take precedence over TOML settings."""
    env = os.environ.get

    if env("ANTHROPIC_API_KEY"):
        settings.keys.anthropic_api_key = env("ANTHROPIC_API_KEY", "")
    if env("OPENAI_API_KEY"):
        settings.keys.openai_api_key = env("OPENAI_API_KEY", "")
    if env("GOOGLE_API_KEY"):
        settings.keys.google_api_key = env("GOOGLE_API_KEY", "")
    if env("OLLAMA_BASE_URL"):
        settings.keys.ollama_base_url = env("OLLAMA_BASE_URL", "http://localhost:11434")

    if env("LLM_PROVIDER"):
        settings.models.default_provider = env("LLM_PROVIDER", "anthropic")

    provider_model_map = {
        "ANTHROPIC_MODEL": None,
        "OPENAI_MODEL": None,
        "GOOGLE_MODEL": None,
        "OLLAMA_MODEL": None,
    }
    current_provider = settings.models.default_provider
    env_model_key = f"{current_provider.upper()}_MODEL"
    if env(env_model_key):
        settings.models.default_model = env(env_model_key, settings.models.default_model)

    for task in ("plan", "code", "explore", "research", "design", "review", "summarize"):
        val = env(f"ROUTE_{task.upper()}", "")
        if val and ":" in val:
            prov, model = val.split(":", 1)
            setattr(settings.models.routing, task, f"{prov.strip()}/{model.strip()}")
