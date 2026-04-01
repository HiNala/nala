"""
Configuration management for Nala.

Config is loaded from (in order of precedence):
  1. Environment variables
  2. .env file in the project root
  3. .env file in the user's home directory (~/.nala/.env)
  4. Defaults

Usage:
    config = Config.load()
    print(config.llm_provider)  # "anthropic"
    print(config.has_llm())     # True if an API key is set
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

LLMProvider = Literal["anthropic", "openai", "google", "ollama"]


class Config(BaseModel):
    """All runtime configuration for the Nala orchestrator."""

    # ── LLM settings ──────────────────────────────────────────────────────

    llm_provider: LLMProvider = Field(
        default="anthropic",
        description="Which LLM provider to use.",
    )
    anthropic_api_key: Optional[str] = Field(default=None)
    openai_api_key: Optional[str] = Field(default=None)
    google_api_key: Optional[str] = Field(default=None)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="codellama:13b")

    # Default model names per provider
    anthropic_model: str = Field(default="claude-sonnet-4-6")
    openai_model: str = Field(default="gpt-4o")
    google_model: str = Field(default="gemini-2.0-flash")

    # ── Neo4j settings ────────────────────────────────────────────────────

    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: Optional[str] = Field(default=None)
    neo4j_enabled: bool = Field(default=False)

    # ── Project settings ──────────────────────────────────────────────────

    project_root: Path = Field(default_factory=Path.cwd)
    session_dir_name: str = Field(default=".nala")
    max_context_tokens: int = Field(default=100_000)

    # ── Dashboard settings ────────────────────────────────────────────────

    dashboard_port: int = Field(default=3000)
    dashboard_enabled: bool = Field(default=False)

    @model_validator(mode="after")
    def resolve_neo4j_enabled(self) -> "Config":
        """Auto-enable Neo4j if a password is provided."""
        if self.neo4j_password and not self.neo4j_enabled:
            object.__setattr__(self, "neo4j_enabled", True)
        return self

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls, project_root: Optional[Path] = None) -> "Config":
        """Load configuration from environment and .env files."""
        root = project_root or Path.cwd()

        # Load .env files (project root first, then home)
        project_env = root / ".env"
        home_env = Path.home() / ".nala" / ".env"

        if project_env.exists():
            load_dotenv(project_env)
        elif home_env.exists():
            load_dotenv(home_env)

        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "anthropic"),  # type: ignore
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            google_api_key=os.environ.get("GOOGLE_API_KEY"),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "codellama:13b"),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            google_model=os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash"),
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD"),
            neo4j_enabled=os.environ.get("NEO4J_ENABLED", "false").lower() == "true",
            project_root=root,
            dashboard_port=int(os.environ.get("DASHBOARD_PORT", "3000")),
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def has_llm(self) -> bool:
        """Return True if at least one LLM API key is configured."""
        return bool(
            self.anthropic_api_key
            or self.openai_api_key
            or self.google_api_key
            or self.llm_provider == "ollama"
        )

    def active_api_key(self) -> Optional[str]:
        """Return the API key for the currently selected provider."""
        match self.llm_provider:
            case "anthropic":
                return self.anthropic_api_key
            case "openai":
                return self.openai_api_key
            case "google":
                return self.google_api_key
            case "ollama":
                return None
            case _:
                return None

    def active_model(self) -> str:
        """Return the model name for the currently selected provider."""
        match self.llm_provider:
            case "anthropic":
                return self.anthropic_model
            case "openai":
                return self.openai_model
            case "google":
                return self.google_model
            case "ollama":
                return self.ollama_model
            case _:
                return "unknown"

    def session_dir(self) -> Path:
        """Return the .nala session directory path."""
        return self.project_root / self.session_dir_name
