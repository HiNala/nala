"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .provider import BaseLLMProvider, LLMMessage, LLMResponse

if TYPE_CHECKING:
    from nala_orchestrator.config import Config


class AnthropicProvider(BaseLLMProvider):
    """Provider for Anthropic's Claude models."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(
                api_key=config.anthropic_api_key or ""
            )
        except ImportError as e:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            ) from e

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:

        anthropic_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self._client.messages.create(**kwargs)
        content = response.content[0].text if response.content else ""

        return LLMResponse(
            content=content,
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "stop",
        )

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        anthropic_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
