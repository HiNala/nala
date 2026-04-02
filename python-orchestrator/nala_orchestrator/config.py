"""
Configuration management for Nala.

Config is loaded from (highest precedence wins):
  1. Environment variables already set in the process
  2. .env file in the project root
  3. .env file in ~/.nala/.env
  4. Built-in defaults

Usage:
    config = Config.load()
    print(config.llm_provider)  # "anthropic"
    print(config.has_llm())     # True if an API key is set
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

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
    anthropic_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    google_api_key: str | None = Field(default=None)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="codellama:13b")

    # Default model names per provider
    anthropic_model: str = Field(default="claude-sonnet-4-6")
    openai_model: str = Field(default="gpt-4o")
    google_model: str = Field(default="gemini-2.0-flash")

    # ── Neo4j settings ────────────────────────────────────────────────────

    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str | None = Field(default=None)
    neo4j_enabled: bool = Field(default=False)

    # ── Multi-model routing overrides ──────────────────────────────────
    # Format: ROUTE_<TASK>=<provider>:<model>  e.g. ROUTE_PLAN=anthropic:claude-opus-4-6
    model_overrides: dict[str, tuple[str, str]] = Field(default_factory=dict)

    # ── Project settings ──────────────────────────────────────────────────

    project_root: Path = Field(default_factory=Path.cwd)
    session_dir_name: str = Field(default=".nala")
    max_context_tokens: int = Field(default=100_000)

    # ── Dashboard settings ────────────────────────────────────────────────

    dashboard_port: int = Field(default=3000)
    dashboard_enabled: bool = Field(default=False)

    @model_validator(mode="after")
    def resolve_neo4j_enabled(self) -> Config:
        """Auto-enable Neo4j if a password is provided."""
        if self.neo4j_password and not self.neo4j_enabled:
            object.__setattr__(self, "neo4j_enabled", True)
        return self

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls, project_root: Path | None = None) -> Config:
        """Load configuration from environment and .env files.

        Precedence (highest wins):
          1. Environment variables already set in the process
          2. Project-root .env file
          3. Home directory ~/.nala/.env
          4. Built-in defaults
        """
        root = project_root or Path.cwd()

        home_env = Path.home() / ".nala" / ".env"

        if home_env.exists():
            load_dotenv(home_env, override=False)
        # Walk upward from project_root so launching from a subdirectory
        # (for example `rust-core`) still picks up repo-level `.env`.
        candidate_envs: list[Path] = []
        cursor = root.resolve()
        while True:
            env_path = cursor / ".env"
            if env_path.exists():
                candidate_envs.append(env_path)
            parent = cursor.parent
            if parent == cursor:
                break
            cursor = parent
        for env_path in reversed(candidate_envs):
            load_dotenv(env_path, override=True)

        def _int(key: str, default: int) -> int:
            raw = os.environ.get(key)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        overrides: dict[str, tuple[str, str]] = {}
        for task in ("plan", "code", "explore", "research", "design", "review", "summarize"):
            val = os.environ.get(f"ROUTE_{task.upper()}", "")
            if ":" in val:
                prov, model = val.split(":", 1)
                overrides[task] = (prov.strip(), model.strip())

        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "anthropic"),  # type: ignore[arg-type]
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            google_api_key=os.environ.get("GOOGLE_API_KEY"),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "codellama:13b"),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            google_model=os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash"),
            model_overrides=overrides,
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD"),
            neo4j_enabled=os.environ.get("NEO4J_ENABLED", "false").lower() == "true",
            project_root=root,
            max_context_tokens=_int("MAX_CONTEXT_TOKENS", 100_000),
            dashboard_port=_int("DASHBOARD_PORT", 3000),
            dashboard_enabled=os.environ.get("DASHBOARD_ENABLED", "false").lower() == "true",
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

    def active_api_key(self) -> str | None:
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
