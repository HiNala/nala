"""Google (Gemini) LLM provider."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from .provider import BaseLLMProvider, LLMMessage, LLMResponse

if TYPE_CHECKING:
    from nala_orchestrator.config import Config

log = logging.getLogger("nala.google")


class GoogleProvider(BaseLLMProvider):
    """Provider for Google's Gemini models."""

    def __init__(self, config: Config, model_override: str | None = None) -> None:
        super().__init__(config, model_override=model_override)
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

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict],
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Single-round chat with function calling via Gemini's tool API.

        Converts OpenAI-format tool schemas to Gemini FunctionDeclaration objects,
        runs the request, then normalises the response back to the OpenAI-compatible
        dict expected by tool_executor.run_tool_loop.
        """
        import asyncio

        try:
            from google.generativeai.types import FunctionDeclaration, Tool
        except ImportError:
            # Older SDK: fall back to text-only via a structured prompt
            return await self._chat_with_tools_text_fallback(
                messages, tools, system_prompt, max_tokens
            )

        # Build Gemini tool declarations from OpenAI-format schemas
        declarations = []
        for t in tools:
            if t.get("type") == "function":
                fn = t["function"]
                declarations.append(
                    FunctionDeclaration(
                        name=fn["name"],
                        description=fn.get("description", ""),
                        parameters=fn.get("parameters", {}),
                    )
                )

        gemini_tools = [Tool(function_declarations=declarations)] if declarations else []

        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_prompt,
            tools=gemini_tools,
        )

        # Convert OpenAI-format history → Gemini history, including tool results.
        # Gemini represents function results as user-role parts with function_response.
        history = _build_gemini_history(messages[:-1])
        chat = model.start_chat(history=history)

        # Last message: if it's a tool result, wrap it as a function_response part;
        # otherwise send it as plain text.
        last_msg = messages[-1] if messages else {}
        last_role = last_msg.get("role", "user")
        if last_role == "tool":
            # Find the tool name from the assistant's most recent tool_calls in history
            tool_name = _find_tool_name(messages[:-1], last_msg.get("tool_call_id", ""))
            last_parts = [{
                "function_response": {
                    "name": tool_name or "unknown",
                    "response": {"result": str(last_msg.get("content", ""))},
                }
            }]
        else:
            last_content = last_msg.get("content", "")
            last_parts = [last_content] if last_content else ["(continue)"]

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: chat.send_message(last_parts)
        )

        # Normalise to OpenAI-compatible dict
        result: dict[str, Any] = {"role": "assistant", "content": ""}
        tool_calls = []
        text_parts = []

        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append({
                    "id": f"call_{fc.name}_{len(tool_calls)}",
                    "type": "function",
                    "function": {
                        "name": fc.name,
                        "arguments": json.dumps(dict(fc.args)),
                    },
                })
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)

        result["content"] = "".join(text_parts)
        if tool_calls:
            result["tool_calls"] = tool_calls

        return result

    async def _chat_with_tools_text_fallback(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict],
        system_prompt: str | None,
        max_tokens: int,
    ) -> dict:
        """Fallback: emit a structured JSON prompt asking the model to call tools.

        Used when the Gemini SDK version doesn't support FunctionDeclaration.
        The model is asked to respond in a JSON envelope so tool_executor can
        still parse tool calls.
        """
        tool_names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        tool_list = "\n".join(f"- {n}" for n in tool_names)
        injection = (
            f"\n\nYou have these tools available: {tool_list}.\n"
            "If you need to call a tool, respond ONLY with valid JSON like:\n"
            '{"tool": "<name>", "args": {...}}\n'
            "Otherwise respond normally."
        )
        # Append to system
        combined_system = (system_prompt or "") + injection

        # Flatten to LLMMessage list for regular chat
        llm_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            if role in ("user", "assistant"):
                llm_messages.append(LLMMessage(role=role, content=msg.get("content", "")))

        resp = await self.chat(llm_messages, system_prompt=combined_system, max_tokens=max_tokens)
        text = resp.content.strip()

        # Try to parse a tool call from JSON response
        if text.startswith("{") and '"tool"' in text:
            try:
                data = json.loads(text)
                if "tool" in data:
                    return {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": f"call_{data['tool']}_0",
                            "type": "function",
                            "function": {
                                "name": data["tool"],
                                "arguments": json.dumps(data.get("args", {})),
                            },
                        }],
                    }
            except json.JSONDecodeError:
                pass

        return {"role": "assistant", "content": text}

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

        history = []
        for msg in messages[:-1]:
            role = "user" if msg.role == "user" else "model"
            history.append({"role": role, "parts": [msg.content]})

        last_msg = messages[-1].content if messages else ""
        chat_session = model.start_chat(history=history)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: chat_session.send_message(last_msg, stream=True),
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text


# ── Gemini history conversion helpers ────────────────────────────────────────

def _build_gemini_history(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-format message list to Gemini chat history format.

    Gemini history is a list of {"role": "user"|"model", "parts": [...]}.
    Tool results (role="tool") become user-role function_response parts and
    are batched with other tool results that belong to the same assistant turn.
    """
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "assistant" and msg.get("tool_calls"):
            # Model turn: mix text + function_call parts
            parts: list = []
            if content:
                parts.append(content)
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                raw_args = fn.get("arguments", "{}")
                try:
                    args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args_dict = {}
                parts.append({"function_call": {"name": fn.get("name", ""), "args": args_dict}})
            out.append({"role": "model", "parts": parts})

        elif role == "tool":
            # Find tool name from the preceding assistant turn's tool_calls
            tool_name = _find_tool_name(messages, msg.get("tool_call_id", ""))
            result_part = {
                "function_response": {
                    "name": tool_name or "unknown",
                    "response": {"result": str(content)},
                }
            }
            # Batch consecutive tool results into one user-role turn
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["parts"], list):
                if any(isinstance(p, dict) and "function_response" in p for p in out[-1]["parts"]):
                    out[-1]["parts"].append(result_part)
                    continue
            out.append({"role": "user", "parts": [result_part]})

        elif role == "assistant":
            out.append({"role": "model", "parts": [str(content)]})

        else:  # user / system
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["parts"], list):
                if all(isinstance(p, str) for p in out[-1]["parts"]):
                    # Merge consecutive plain-text user messages
                    out[-1]["parts"][0] += "\n\n" + str(content)
                    continue
            out.append({"role": "user", "parts": [str(content)]})

    return out


def _find_tool_name(messages: list[dict], tool_call_id: str) -> str:
    """Search message history for the tool name that matches a tool_call_id."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                if tc.get("id") == tool_call_id:
                    return tc.get("function", {}).get("name", "")
    return ""
