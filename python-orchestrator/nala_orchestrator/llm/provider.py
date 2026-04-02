"""
Base LLM provider interface and factory.

All providers implement BaseLLMProvider. The factory function `create_provider`
returns the correct provider based on the Config's llm_provider setting.

Adding a new provider:
  1. Create a new file (e.g. my_provider.py) with a class that extends BaseLLMProvider
  2. Add it to the `create_provider` factory match statement
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

    def __init__(self, config: Config) -> None:
        self.config = config

    @property
    def model(self) -> str:
        """The model identifier for this provider."""
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

    def health_check(self) -> bool:
        """Return True if the provider appears to be configured correctly."""
        return bool(self.config.active_api_key() or self.config.llm_provider == "ollama")


# ── Factory ────────────────────────────────────────────────────────────────


def create_provider(config: Config) -> BaseLLMProvider:
    """Instantiate the correct provider based on config.llm_provider."""
    match config.llm_provider:
        case "anthropic":
            from .anthropic_provider import AnthropicProvider
            return AnthropicProvider(config)
        case "openai":
            from .openai_provider import OpenAIProvider
            return OpenAIProvider(config)
        case "google":
            from .google_provider import GoogleProvider
            return GoogleProvider(config)
        case "ollama":
            from .ollama_provider import OllamaProvider
            return OllamaProvider(config)
        case _:
            raise ValueError(
                f"Unknown LLM provider: '{config.llm_provider}'. "
                "Valid options: anthropic, openai, google, ollama"
            )
