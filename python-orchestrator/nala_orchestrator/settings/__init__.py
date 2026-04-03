"""User-facing settings system for Nala.

Manages `.nala/settings.toml` as the canonical configuration file,
with fallback to `.env` and `~/.nala/settings.toml`.
"""

from .loader import SettingsLoader
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
from .writer import SettingsWriter

__all__ = [
    "AgentGitSettings",
    "AgentSettings",
    "AgentVerificationSettings",
    "DisplaySettings",
    "KeysSettings",
    "ModelRoutingSettings",
    "ModelsSettings",
    "NalaSettings",
    "SettingsLoader",
    "SettingsWriter",
]
