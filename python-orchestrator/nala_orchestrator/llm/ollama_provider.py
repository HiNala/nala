"""Ollama local model provider."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx

from .provider import BaseLLMProvider, LLMMessage, LLMResponse

if TYPE_CHECKING:
    from nala_orchestrator.config import Config

log = logging.getLogger("nala.ollama")


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

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Single-round chat with tool calling via Ollama's /api/chat endpoint.

        Ollama supports the OpenAI tool-calling format since v0.1.20 for models
        like mistral-nemo, llama3.1, qwen2.5, etc.  Older models / Ollama versions
        fall back to a structured-prompt approach so the tool loop still functions.
        """
        all_messages: list[dict] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": all_messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120) as client:
            try:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                log.warning("Ollama tool call failed (%s), using text fallback", exc)
                return await self._chat_with_tools_text_fallback(
                    messages, tools, system_prompt, max_tokens
                )

        msg = data.get("message", {})
        result: dict[str, Any] = {
            "role": "assistant",
            "content": msg.get("content", ""),
        }

        # Ollama returns tool_calls in the same format as OpenAI
        if msg.get("tool_calls"):
            result["tool_calls"] = [
                {
                    "id": tc.get("id", f"call_{i}"),
                    "type": "function",
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": json.dumps(tc.get("function", {}).get("arguments", {}))
                        if not isinstance(tc.get("function", {}).get("arguments"), str)
                        else tc["function"]["arguments"],
                    },
                }
                for i, tc in enumerate(msg["tool_calls"])
            ]

        return result

    async def _chat_with_tools_text_fallback(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict],
        system_prompt: str | None,
        max_tokens: int,
    ) -> dict:
        """Text-prompt fallback for Ollama models that don't support tool calling."""
        tool_descs = []
        for t in tools:
            if t.get("type") == "function":
                fn = t["function"]
                params = fn.get("parameters", {})
                props = params.get("properties", {})
                param_list = ", ".join(
                    f"{k}: {v.get('type','any')}" for k, v in props.items()
                )
                tool_descs.append(f"- {fn['name']}({param_list}): {fn.get('description','')}")

        tool_section = "\n".join(tool_descs)
        injection = (
            f"\n\nAvailable tools:\n{tool_section}\n\n"
            "To call a tool, respond with ONLY this JSON (no other text):\n"
            '{"tool":"<name>","args":{...}}\n'
            "Otherwise respond normally."
        )
        combined = (system_prompt or "") + injection

        llm_msgs: list[dict] = []
        if combined:
            llm_msgs.append({"role": "system", "content": combined})
        for msg in messages:
            role = msg.get("role", "user")
            if role in ("user", "assistant"):
                llm_msgs.append({"role": role, "content": msg.get("content", "")})

        payload = {
            "model": self.model,
            "messages": llm_msgs,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        text = data.get("message", {}).get("content", "").strip()

        # Try to parse a tool call from the structured JSON response
        if text.startswith("{") and '"tool"' in text:
            try:
                call_data = json.loads(text)
                if "tool" in call_data:
                    return {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": f"call_{call_data['tool']}_0",
                            "type": "function",
                            "function": {
                                "name": call_data["tool"],
                                "arguments": json.dumps(call_data.get("args", {})),
                            },
                        }],
                    }
            except json.JSONDecodeError:
                pass

        return {"role": "assistant", "content": text}

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
