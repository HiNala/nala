"""Google (Gemini) LLM provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .provider import BaseLLMProvider, LLMMessage, LLMResponse

if TYPE_CHECKING:
    from nala_orchestrator.config import Config


class GoogleProvider(BaseLLMProvider):
    """Provider for Google's Gemini models."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        try:
            import google.generativeai as genai
            genai.configure(api_key=config.google_api_key or "")
            self._genai = genai
        except ImportError as e:
            raise ImportError(
                "google-generativeai not installed. Run: pip install google-generativeai"
            ) from e

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import asyncio

        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_prompt,
        )

        # Convert messages to Gemini format
        history = []
        for msg in messages[:-1]:
            role = "user" if msg.role == "user" else "model"
            history.append({"role": role, "parts": [msg.content]})

        chat = model.start_chat(history=history)
        last_msg = messages[-1].content if messages else ""

        # Gemini SDK is sync — run in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: chat.send_message(last_msg)
        )

        return LLMResponse(
            content=response.text,
            model=self.model,
        )

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        import asyncio

        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_prompt,
        )

        last_msg = messages[-1].content if messages else ""
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(last_msg, stream=True),
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text
