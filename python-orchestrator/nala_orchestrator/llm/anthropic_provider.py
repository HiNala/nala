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

        anthropic_messages = self._convert_messages(messages)

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
        anthropic_messages = self._convert_messages(messages)

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

    @staticmethod
    def _convert_messages(
        messages: list[LLMMessage],
    ) -> list[dict[str, str]]:
        """Convert messages for the Anthropic API.

        Mid-conversation ``system`` messages (e.g. compaction summaries)
        are re-roled as ``user`` so they aren't silently dropped.
        """
        out: list[dict[str, str]] = []
        for m in messages:
            role = m.role
            if role == "system":
                role = "user"
            if out and out[-1]["role"] == role:
                out[-1]["content"] += "\n\n" + m.content
            else:
                out.append({"role": role, "content": m.content})
        return out
