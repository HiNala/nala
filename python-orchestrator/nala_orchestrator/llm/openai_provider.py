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

    def __init__(self, config: Config, model_override: str | None = None) -> None:
        super().__init__(config, model_override=model_override)
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
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(
            {"role": m.role, "content": m.content} for m in messages
        )

        log.debug("stream_chat starting (true streaming)")
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                max_tokens=max_tokens,
                stream=True,
            )
            async for event in stream:
                delta = event.choices[0].delta if event.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:
            log.error("OpenAI streaming failed: %s", exc)
            yield f"\n\nError: {exc}"
