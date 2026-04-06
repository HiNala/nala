"""
Base LLM provider interface and factory.

All providers implement BaseLLMProvider. The factory functions create providers:
  - `create_provider(config)` — uses the primary configured provider
  - `create_provider_for(provider, model, config)` — targets a specific provider/model

Adding a new provider:
  1. Create a new file (e.g. my_provider.py) with a class that extends BaseLLMProvider
  2. Add it to the `_make_provider` factory match statement
  3. Add the API key field to Config
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nala_orchestrator.config import Config


# ── Data types ─────────────────────────────────────────────────────────────


@dataclass
class LLMMessage:
    """A single message in a conversation."""

    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class LLMResponse:
    """A complete (non-streaming) response from an LLM."""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"


# ── Base class ─────────────────────────────────────────────────────────────


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(self, config: Config, model_override: str | None = None) -> None:
        self.config = config
        self._model_override = model_override

    @property
    def model(self) -> str:
        """The model identifier for this provider."""
        if self._model_override:
            return self._model_override
        return self.config.active_model()

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a conversation and return a complete response."""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream a response token-by-token. Yields text chunks."""
        ...

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Single-round chat that may return tool_calls.

        All concrete providers override this.  The default raises so that
        a missing implementation is caught at runtime with a clear message.

        Returns an OpenAI-compatible assistant message dict:
          {"role": "assistant", "content": "...", "tool_calls": [...]}
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement chat_with_tools. "
            "Implement it or use a provider that supports tool calling."
        )

    def health_check(self) -> bool:
        """Return True if the provider appears to be configured correctly."""
        return bool(self.config.active_api_key() or self.config.llm_provider == "ollama")


# ── Factory ────────────────────────────────────────────────────────────────


def _make_provider(
    provider_name: str,
    config: Config,
    model_override: str | None = None,
) -> BaseLLMProvider:
    """Internal factory — creates a provider instance by name."""
    match provider_name:
        case "anthropic":
            from .anthropic_provider import AnthropicProvider
            return AnthropicProvider(config, model_override=model_override)
        case "openai":
            from .openai_provider import OpenAIProvider
            return OpenAIProvider(config, model_override=model_override)
        case "google":
            from .google_provider import GoogleProvider
            return GoogleProvider(config, model_override=model_override)
        case "ollama":
            from .ollama_provider import OllamaProvider
            return OllamaProvider(config, model_override=model_override)
        case _:
            raise ValueError(
                f"Unknown LLM provider: '{provider_name}'. "
                "Valid options: anthropic, openai, google, ollama"
            )


def create_provider(config: Config) -> BaseLLMProvider:
    """Instantiate the correct provider based on config.llm_provider."""
    return _make_provider(config.llm_provider, config)


def create_provider_for(
    provider_name: str,
    model_id: str,
    config: Config,
) -> BaseLLMProvider:
    """Create a provider targeting a specific provider and model.

    Used by the model router to send different tasks to different models.
    The provider still reads API keys from config, but the model is overridden.
    """
    return _make_provider(provider_name, config, model_override=model_id)
