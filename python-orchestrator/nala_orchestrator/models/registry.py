"""Model registry — discovers and persists available models from configured API keys."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .catalog import BUNDLED_CATALOG, find_model, models_for_provider
from .types import ModelInfo, Provider, ProviderStatus

if TYPE_CHECKING:
    from nala_orchestrator.config import Config

log = logging.getLogger(__name__)

REGISTRY_FILE = "models/registry.json"


class ModelRegistry:
    """Discovers which providers are live and which models are accessible.

    The registry is persisted to `.nala/models/registry.json` so it only
    needs a full rebuild on explicit refresh.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._statuses: dict[Provider, ProviderStatus] = {}
        self._available: dict[Provider, list[ModelInfo]] = {}
        self._registry_path = config.project_root / config.session_dir_name / REGISTRY_FILE
        self._loaded = False

    # ── Public API ──────────────────────────────────────────────────────

    async def ensure_loaded(self) -> None:
        """Load from cache or build fresh if needed."""
        if self._loaded:
            return
        if self._registry_path.exists():
            try:
                self._load_from_disk()
                self._loaded = True
                return
            except Exception:
                log.warning("Corrupt registry cache — rebuilding")
        await self.refresh()

    async def refresh(self) -> None:
        """Probe every configured provider and rebuild the registry."""
        self._statuses.clear()
        self._available.clear()

        for provider in Provider:
            status = await self._probe_provider(provider)
            self._statuses[provider] = status
            if status.key_valid:
                models = models_for_provider(provider)
                self._available[provider] = models
            else:
                self._available[provider] = []

        self._persist()
        self._loaded = True
        log.info("Model registry refreshed: %d providers active", self.active_provider_count)

    @property
    def active_provider_count(self) -> int:
        return sum(1 for s in self._statuses.values() if s.key_valid)

    def get_status(self, provider: Provider) -> ProviderStatus | None:
        return self._statuses.get(provider)

    def all_statuses(self) -> list[ProviderStatus]:
        return list(self._statuses.values())

    def available_models(self, provider: Provider | None = None) -> list[ModelInfo]:
        """Return available models, optionally filtered by provider."""
        if provider is not None:
            return list(self._available.get(provider, []))
        return [m for models in self._available.values() for m in models]

    def is_provider_available(self, provider: Provider) -> bool:
        s = self._statuses.get(provider)
        return s is not None and s.key_valid

    def best_available_provider(self) -> Provider | None:
        """Return the first available provider in preference order."""
        pref_order = [Provider.ANTHROPIC, Provider.OPENAI, Provider.GOOGLE, Provider.OLLAMA]
        for p in pref_order:
            if self.is_provider_available(p):
                return p
        return None

    def find_model(self, model_id: str) -> ModelInfo | None:
        """Look up a model by ID among available models."""
        for m in self.available_models():
            if m.id == model_id:
                return m
        return find_model(model_id)

    def format_status_report(self) -> str:
        """Human-readable status for /models display."""
        lines: list[str] = ["## Available Models\n"]

        for provider in Provider:
            status = self._statuses.get(provider)
            if status is None:
                continue

            if status.key_valid:
                icon = "+"
            elif status.key_present:
                icon = "!"
            else:
                icon = "-"

            header = f"### [{icon}] {provider.value.title()}"
            if status.error:
                header += f"  ({status.error})"
            lines.append(header)

            if status.key_valid:
                models = self._available.get(provider, [])
                if models:
                    for m in models:
                        tasks = ", ".join(t.value for t in sorted(m.recommended_tasks, key=lambda t: t.value))
                        cost = f"${m.input_cost_per_mtok:.2f}/${m.output_cost_per_mtok:.2f}" if m.input_cost_per_mtok > 0 else "free"
                        lines.append(
                            f"  - **{m.display_name}** (`{m.id}`)  "
                            f"ctx:{m.context_window // 1000}K  "
                            f"{m.cost_tier.value}  {cost}  "
                            f"best for: {tasks}"
                        )
                else:
                    lines.append("  _(no models in catalog)_")
            elif not status.key_present:
                lines.append(f"  No API key configured. Set `{_env_var_for(provider)}` in `.env`.")
            else:
                lines.append(f"  Key present but invalid: {status.error or 'unknown error'}")

            lines.append("")

        active = self.active_provider_count
        total = len(Provider)
        lines.append(f"**{active}/{total}** providers active. Use `/model` to see current routing.")
        return "\n".join(lines)

    # ── Provider probing ────────────────────────────────────────────────

    async def _probe_provider(self, provider: Provider) -> ProviderStatus:
        """Check if a provider's API key is present and valid."""
        key = self._get_key(provider)
        if key is None and provider != Provider.OLLAMA:
            return ProviderStatus(provider=provider, key_present=False, key_valid=False)

        status = ProviderStatus(provider=provider, key_present=True)

        try:
            if provider == Provider.ANTHROPIC:
                await self._probe_anthropic(key, status)
            elif provider == Provider.OPENAI:
                await self._probe_openai(key, status)
            elif provider == Provider.GOOGLE:
                await self._probe_google(key, status)
            elif provider == Provider.OLLAMA:
                await self._probe_ollama(status)
        except Exception as e:
            status.key_valid = False
            status.error = str(e)[:120]
            log.warning("Failed to probe %s: %s", provider.value, e)

        return status

    async def _probe_anthropic(self, key: str | None, status: ProviderStatus) -> None:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=key)
            resp = await client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            status.key_valid = True
            status.available_models = [m.id for m in models_for_provider(Provider.ANTHROPIC)]
        except Exception as e:
            err = str(e).lower()
            if "authentication" in err or "api key" in err or "invalid" in err:
                status.key_valid = False
                status.error = "Invalid API key"
            else:
                status.key_valid = True
                status.error = f"Probe warning: {str(e)[:80]}"
                status.available_models = [m.id for m in models_for_provider(Provider.ANTHROPIC)]

    async def _probe_openai(self, key: str | None, status: ProviderStatus) -> None:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=key)
            models_resp = await client.models.list()
            status.key_valid = True
            remote_ids = {m.id for m in models_resp.data}
            catalog_ids = [m.id for m in models_for_provider(Provider.OPENAI)]
            status.available_models = [mid for mid in catalog_ids if mid in remote_ids] or catalog_ids
        except Exception as e:
            err = str(e).lower()
            if "authentication" in err or "api key" in err or "invalid" in err:
                status.key_valid = False
                status.error = "Invalid API key"
            else:
                status.key_valid = True
                status.error = f"Probe warning: {str(e)[:80]}"
                status.available_models = [m.id for m in models_for_provider(Provider.OPENAI)]

    async def _probe_google(self, key: str | None, status: ProviderStatus) -> None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            _models = genai.list_models()
            status.key_valid = True
            status.available_models = [m.id for m in models_for_provider(Provider.GOOGLE)]
        except Exception as e:
            err = str(e).lower()
            if "api key" in err or "invalid" in err or "permission" in err:
                status.key_valid = False
                status.error = "Invalid API key"
            else:
                status.key_valid = True
                status.error = f"Probe warning: {str(e)[:80]}"
                status.available_models = [m.id for m in models_for_provider(Provider.GOOGLE)]

    async def _probe_ollama(self, status: ProviderStatus) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._config.ollama_base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    remote_models = [m.get("name", "") for m in data.get("models", [])]
                    status.key_valid = True
                    status.available_models = remote_models or [m.id for m in models_for_provider(Provider.OLLAMA)]
                else:
                    status.key_valid = False
                    status.error = f"Ollama returned {resp.status_code}"
        except Exception:
            status.key_valid = False
            status.error = "Ollama not running"
            status.key_present = False

    # ── Key helpers ─────────────────────────────────────────────────────

    def _get_key(self, provider: Provider) -> str | None:
        match provider:
            case Provider.ANTHROPIC:
                return self._config.anthropic_api_key
            case Provider.OPENAI:
                return self._config.openai_api_key
            case Provider.GOOGLE:
                return self._config.google_api_key
            case Provider.OLLAMA:
                return None

    # ── Persistence ─────────────────────────────────────────────────────

    def _persist(self) -> None:
        """Save registry to disk."""
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": time.time(),
            "providers": {},
        }
        for provider, status in self._statuses.items():
            data["providers"][provider.value] = {
                "key_present": status.key_present,
                "key_valid": status.key_valid,
                "available_models": status.available_models,
                "error": status.error,
            }
        self._registry_path.write_text(json.dumps(data, indent=2))

    def _load_from_disk(self) -> None:
        """Restore from persisted JSON."""
        raw = json.loads(self._registry_path.read_text())
        for prov_name, pdata in raw.get("providers", {}).items():
            try:
                provider = Provider(prov_name)
            except ValueError:
                continue
            self._statuses[provider] = ProviderStatus(
                provider=provider,
                key_present=pdata.get("key_present", False),
                key_valid=pdata.get("key_valid", False),
                available_models=pdata.get("available_models", []),
                error=pdata.get("error"),
            )
            if pdata.get("key_valid"):
                self._available[provider] = models_for_provider(provider)
            else:
                self._available[provider] = []


def _env_var_for(provider: Provider) -> str:
    return {
        Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
        Provider.OPENAI: "OPENAI_API_KEY",
        Provider.GOOGLE: "GOOGLE_API_KEY",
        Provider.OLLAMA: "OLLAMA_BASE_URL",
    }.get(provider, "???")
