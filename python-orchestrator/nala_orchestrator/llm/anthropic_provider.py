"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from .provider import BaseLLMProvider, LLMMessage, LLMResponse

if TYPE_CHECKING:
    from nala_orchestrator.config import Config

log = logging.getLogger("nala.anthropic")


class AnthropicProvider(BaseLLMProvider):
    """Provider for Anthropic's Claude models."""

    def __init__(self, config: Config, model_override: str | None = None) -> None:
        super().__init__(config, model_override=model_override)
        try:
            import anthropic
            # Override the SDK default (600 s) with sane per-operation timeouts.
            # connect=5s, read=30s, write=10s, pool=5s.
            self._client = anthropic.AsyncAnthropic(
                api_key=config.anthropic_api_key or "",
                timeout=anthropic.Timeout(
                    connect=5.0,
                    read=30.0,
                    write=10.0,
                    pool=5.0,
                ),
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

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Single-round chat that may return tool_calls.

        Converts OpenAI-format tool schemas and message history to Anthropic's
        tool_use format, then normalises the response back to the OpenAI-compatible
        dict expected by tool_executor.run_tool_loop.
        """
        # Convert OpenAI-format tool definitions → Anthropic format
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                fn = tool["function"]
                anthropic_tools.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get(
                        "parameters",
                        {"type": "object", "properties": {}, "required": []},
                    ),
                })

        # Convert message history (which may contain tool results) → Anthropic format
        anthropic_messages = self._convert_tool_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        log.debug("Anthropic tool call: model=%s tools=%d msgs=%d",
                  self.model, len(anthropic_tools), len(anthropic_messages))

        response = await self._client.messages.create(**kwargs)

        # Normalise response → OpenAI-compatible dict
        result: dict[str, Any] = {"role": "assistant", "content": ""}
        tool_calls: list[dict] = []
        text_parts: list[str] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    },
                })

        result["content"] = "".join(text_parts)
        if tool_calls:
            result["tool_calls"] = tool_calls

        log.debug("Anthropic response: tool_calls=%d text=%d chars",
                  len(tool_calls), len(result["content"]))
        return result

    @staticmethod
    def _convert_tool_messages(messages: list[dict[str, Any]]) -> list[dict]:
        """Convert OpenAI-style message history (including tool results) to Anthropic format.

        OpenAI uses role="tool" + tool_call_id for tool results.
        Anthropic uses role="user" + content=[{"type":"tool_result",...}].

        Critical: Anthropic requires strictly alternating user/assistant roles.
        When an assistant emits multiple parallel tool calls, all their results
        arrive as consecutive role="tool" messages that must be batched into a
        SINGLE role="user" message with multiple tool_result blocks.
        """
        out: list[dict] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "tool":
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": str(content),
                }
                # Batch consecutive tool results into the same user message
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(result_block)
                else:
                    out.append({"role": "user", "content": [result_block]})

            elif role == "assistant" and msg.get("tool_calls"):
                # Assistant turn that invoked tools — emit as a list of content blocks
                blocks: list[dict] = []
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", "{}")
                    try:
                        parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except json.JSONDecodeError:
                        parsed = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": parsed,
                    })
                out.append({"role": "assistant", "content": blocks})

            else:
                # Regular user or assistant message
                if (out and out[-1]["role"] == role
                        and isinstance(out[-1]["content"], str)):
                    # Merge consecutive same-role plain-text messages
                    out[-1]["content"] += "\n\n" + str(content)
                else:
                    out.append({"role": role, "content": str(content)})

        return out

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
