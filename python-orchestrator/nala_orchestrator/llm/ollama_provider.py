"""Ollama local model provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import httpx

from .provider import BaseLLMProvider, LLMMessage, LLMResponse

if TYPE_CHECKING:
    from nala_orchestrator.config import Config


class OllamaProvider(BaseLLMProvider):
    """Provider for local models served by Ollama."""

    def __init__(self, config: Config, model_override: str | None = None) -> None:
        super().__init__(config, model_override=model_override)
        self.base_url = config.ollama_base_url.rstrip("/")

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content", "")
        return LLMResponse(content=content, model=self.model)

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        import json

        payload = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "stream": True,
            "options": {"num_predict": max_tokens},
        }

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
                    except json.JSONDecodeError:
                        continue

    def health_check(self) -> bool:
        """Ollama doesn't need an API key — always considered configured."""
        return True

    @staticmethod
    def _build_messages(
        messages: list[LLMMessage], system_prompt: str | None
    ) -> list[dict]:
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend({"role": m.role, "content": m.content} for m in messages)
        return result
