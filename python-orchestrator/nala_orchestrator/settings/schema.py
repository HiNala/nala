"""Typed schema for `.nala/settings.toml`."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeysSettings:
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"


@dataclass
class ModelRoutingSettings:
    plan: str = ""
    code: str = ""
    explore: str = ""
    research: str = ""
    design: str = ""
    review: str = ""
    summarize: str = ""

    def as_overrides(self) -> dict[str, tuple[str, str]]:
        """Convert non-empty routing entries to (provider, model) pairs."""
        result: dict[str, tuple[str, str]] = {}
        for task in ("plan", "code", "explore", "research", "design", "review", "summarize"):
            val = getattr(self, task, "")
            if not val:
                continue
            if "/" in val:
                prov, model = val.split("/", 1)
                result[task] = (prov.strip(), model.strip())
            elif ":" in val:
                prov, model = val.split(":", 1)
                result[task] = (prov.strip(), model.strip())
        return result


@dataclass
class ModelsSettings:
    default_provider: str = ""
    default_model: str = ""
    routing: ModelRoutingSettings = field(default_factory=ModelRoutingSettings)


@dataclass
class AgentGitSettings:
    auto_branch: bool = True
    auto_commit: bool = True
    branch_prefix: str = "nala/agent-"


@dataclass
class AgentVerificationSettings:
    auto_verify: bool = True
    verify_timeout: int = 120


@dataclass
class AgentSettings:
    autonomy: str = "guided"
    max_workers: int = 3
    git: AgentGitSettings = field(default_factory=AgentGitSettings)
    verification: AgentVerificationSettings = field(default_factory=AgentVerificationSettings)


@dataclass
class DisplaySettings:
    theme: str = "dark"
    show_startup_hints: bool = True


@dataclass
class NalaSettings:
    """Top-level settings object matching `.nala/settings.toml` structure."""

    keys: KeysSettings = field(default_factory=KeysSettings)
    models: ModelsSettings = field(default_factory=ModelsSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)
    display: DisplaySettings = field(default_factory=DisplaySettings)

    def format_summary(self, provider_statuses: dict[str, bool] | None = None) -> str:
        """Human-readable settings summary for the `/settings` command."""
        lines: list[str] = []

        lines.append("## Provider Keys\n")
        key_entries = [
            ("Anthropic", bool(self.keys.anthropic_api_key)),
            ("OpenAI", bool(self.keys.openai_api_key)),
            ("Google", bool(self.keys.google_api_key)),
            ("Ollama", True),
        ]
        for name, has_key in key_entries:
            icon = "+" if has_key else "x"
            status = "configured" if has_key else "no key"
            extra = ""
            if provider_statuses and name.lower() in provider_statuses:
                live = provider_statuses[name.lower()]
                extra = " (live)" if live else " (key invalid)"
            lines.append(f"  [{icon}] {name}: {status}{extra}")

        lines.append("\n## Default Model\n")
        prov_display = self.models.default_provider or "(auto-detect from keys)"
        model_display = self.models.default_model or "(provider default)"
        lines.append(f"  Provider: {prov_display}")
        lines.append(f"  Model:    {model_display}")

        lines.append("\n## Model Routing\n")
        routing = self.models.routing
        for task in ("plan", "code", "explore", "research", "design", "review", "summarize"):
            val = getattr(routing, task, "")
            if val:
                lines.append(f"  {task:10s} -> {val}")
            else:
                lines.append(f"  {task:10s} -> (default)")

        lines.append("\n## Agent Defaults\n")
        lines.append(f"  Autonomy:    {self.agent.autonomy}")
        lines.append(f"  Max workers: {self.agent.max_workers}")
        git_branch = "yes" if self.agent.git.auto_branch else "no"
        git_commit = "yes" if self.agent.git.auto_commit else "no"
        lines.append(f"  Git: auto-branch {git_branch}, auto-commit {git_commit}")
        lines.append(f"  Verify: auto={self.agent.verification.auto_verify}, timeout={self.agent.verification.verify_timeout}s")

        lines.append("\n## Display\n")
        lines.append(f"  Theme: {self.display.theme}")
        lines.append(f"  Startup hints: {'yes' if self.display.show_startup_hints else 'no'}")

        return "\n".join(lines)
