"""OpenAI (GPT) LLM provider."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .provider import BaseLLMProvider, LLMMessage, LLMResponse

if TYPE_CHECKING:
    from nala_orchestrator.config import Config

log = logging.getLogger("nala.openai")

_TIMEOUT_SECONDS = 90


class OpenAIProvider(BaseLLMProvider):
    """Provider for OpenAI's GPT models."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        try:
            import httpx
            import openai

            self._client = openai.AsyncOpenAI(
                api_key=config.openai_api_key or "",
                timeout=httpx.Timeout(
                    _TIMEOUT_SECONDS,
                    connect=15.0,
                ),
            )
        except ImportError as e:
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            ) from e

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(
            {"role": m.role, "content": m.content} for m in messages
        )

        log.debug(
            "OpenAI request: model=%s, messages=%d, max_tokens=%d",
            self.model, len(all_messages), max_tokens,
        )
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            max_tokens=max_tokens,
        )
        log.debug("OpenAI response received, finish_reason=%s",
                   response.choices[0].finish_reason)

        content = response.choices[0].message.content or ""
        usage = response.usage

        return LLMResponse(
            content=content,
            model=self.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            finish_reason=response.choices[0].finish_reason or "stop",
        )

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        import asyncio

        log.debug("stream_chat starting (non-stream with chunking)")
        try:
            response = await asyncio.wait_for(
                self.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                ),
                timeout=_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            log.error("OpenAI request timed out after %ds", _TIMEOUT_SECONDS)
            yield f"Request timed out after {_TIMEOUT_SECONDS}s. Check your network connection."
            return

        content = response.content or ""
        log.debug("stream_chat got %d chars, chunking", len(content))
        chunk_size = 160
        for start in range(0, len(content), chunk_size):
            yield content[start : start + chunk_size]
