"""Tool executor — runs the LLM ↔ tool-calling loop.

Sends messages + tool definitions to the LLM, executes any tool calls
the model requests, feeds results back, and repeats until the model
produces a final text response (no more tool calls).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from .tool_defs import AGENT_TOOLS

if TYPE_CHECKING:
    from .toolbox import Toolbox
    from ..llm.openai_provider import OpenAIProvider

log = logging.getLogger("nala.tool_executor")

_MAX_ROUNDS = 25


def _dispatch_tool(toolbox: Toolbox, name: str, args: dict) -> str:
    """Call a Toolbox method by name. Returns the result as a string."""
    try:
        match name:
            case "read_file":
                return toolbox.read_file(args.get("path", ""))
            case "write_file":
                return toolbox.write_file(args.get("path", ""), args.get("content", ""))
            case "edit_file":
                return toolbox.edit_file(
                    args.get("path", ""),
                    args.get("old_text", ""),
                    args.get("new_text", ""),
                )
            case "list_files":
                return toolbox.list_files(args.get("directory", ""))
            case "tree":
                return toolbox.tree(
                    args.get("directory", ""),
                    max_depth=args.get("max_depth", 4),
                )
            case "search_code":
                return toolbox.search_code(args.get("query", ""))
            case "get_cwd":
                return toolbox.get_cwd()
            case "run_shell":
                result = toolbox.run_shell(
                    args.get("command", ""),
                    cwd=args.get("cwd", ""),
                )
                return f"exit_code={result['exit_code']}\n{result['output']}"
            case "git_status":
                return toolbox.git_status()
            case "git_diff":
                return toolbox.git_diff()
            case _:
                return f"(unknown tool: {name})"
    except Exception as exc:
        log.error("Tool %s raised: %s", name, exc)
        return f"(tool error: {exc})"


async def run_tool_loop(
    provider: OpenAIProvider,
    toolbox: Toolbox,
    system_prompt: str,
    user_message: str,
    *,
    max_rounds: int = _MAX_ROUNDS,
    max_tokens: int = 4096,
    on_tool_call: Any | None = None,
) -> AsyncIterator[str]:
    """Run the tool-calling loop, yielding text chunks as they arrive.

    ``on_tool_call`` is an optional callback ``(name, args) -> None``
    that gets called each time a tool is invoked (for status updates).
    """
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_message},
    ]

    for round_num in range(max_rounds):
        log.debug("Tool loop round %d, messages=%d", round_num, len(messages))

        assistant_msg = await provider.chat_with_tools(
            messages=messages,
            tools=AGENT_TOOLS,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

        tool_calls = assistant_msg.get("tool_calls")

        if not tool_calls:
            content = assistant_msg.get("content", "")
            if content:
                yield content
            return

        messages.append(assistant_msg)

        for tc in tool_calls:
            fn = tc["function"]
            name = fn["name"]
            try:
                args = json.loads(fn["arguments"])
            except json.JSONDecodeError:
                args = {}

            if on_tool_call:
                on_tool_call(name, args)

            log.info("Tool call: %s(%s)", name, json.dumps(args)[:200])
            yield f"\n`→ {name}({_brief_args(args)})`\n"

            result = _dispatch_tool(toolbox, name, args)

            if len(result) > 20_000:
                result = result[:20_000] + f"\n... (truncated, {len(result)} chars total)"

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        if assistant_msg.get("content"):
            yield assistant_msg["content"]

    yield "\n(reached max tool rounds — stopping)"


def _brief_args(args: dict) -> str:
    """Compact representation of tool arguments for display."""
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:57] + "..."
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)
