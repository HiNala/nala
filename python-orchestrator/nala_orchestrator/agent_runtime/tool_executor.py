"""Tool executor — runs the LLM ↔ tool-calling loop.

Sends messages + tool definitions to the LLM, executes any tool calls
the model requests, feeds results back, and repeats until the model
produces a final text response (no more tool calls).
"""

from __future__ import annotations

import asyncio
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
# Maximum time (seconds) a single tool call is allowed to run.
# Slow shell commands (builds, tests) may legitimately need 120 s.
_TOOL_TIMEOUT = 120

# Character budget for the accumulated message history passed to the LLM.
# At ~4 chars/token this is roughly 20 K tokens — enough for a full work session
# without overflowing a 32 K-token context window even after adding the system prompt.
_HISTORY_CHAR_BUDGET = 80_000


def _dispatch_tool(toolbox: Toolbox, name: str, args: dict) -> str:
    """Call a Toolbox method by name. Returns the result as a string.

    All dispatches are synchronous; async tools (run_analysis, team_*)
    are called from the async wrapper below.
    """
    match name:
        # ── Read / navigate ─────────────────────────────────────────────
        case "read_file":
            return toolbox.read_file(
                args.get("path", ""),
                start_line=int(args.get("start_line", 1)),
                end_line=args.get("end_line"),  # None → read all
            )
        case "file_info":
            return toolbox.file_info(args.get("path", ""))
        case "list_files":
            return toolbox.list_files(args.get("directory", ""))
        case "tree":
            return toolbox.tree(
                args.get("directory", ""),
                max_depth=int(args.get("max_depth", 4)),
            )
        case "find_in_files":
            return toolbox.find_in_files(
                pattern=args.get("pattern", ""),
                directory=args.get("directory", ""),
                file_glob=args.get("file_glob", ""),
                max_results=int(args.get("max_results", 60)),
                ignore_case=bool(args.get("ignore_case", False)),
            )
        case "search_code":
            return toolbox.search_code(args.get("query", ""))
        case "get_cwd":
            return toolbox.get_cwd()

        # ── Write / edit ─────────────────────────────────────────────────
        case "write_file":
            return toolbox.write_file(args.get("path", ""), args.get("content", ""))
        case "edit_file":
            return toolbox.edit_file(
                path=args.get("path", ""),
                old_text=args.get("old_text", ""),
                new_text=args.get("new_text", ""),
                replace_all=bool(args.get("replace_all", False)),
            )
        case "insert_lines":
            return toolbox.insert_lines(
                path=args.get("path", ""),
                line_number=int(args.get("line_number", 1)),
                text=args.get("text", ""),
            )
        case "replace_lines":
            return toolbox.replace_lines(
                path=args.get("path", ""),
                start_line=int(args.get("start_line", 1)),
                end_line=int(args.get("end_line", 1)),
                new_text=args.get("new_text", ""),
            )

        # ── Shell ────────────────────────────────────────────────────────
        case "run_shell":
            timeout = min(int(args.get("timeout", 60)), 300)  # cap at 5 min
            result = toolbox.run_shell(
                args.get("command", ""),
                cwd=args.get("cwd", ""),
                timeout=timeout,
            )
            lines = [f"exit_code={result['exit_code']}", result["output"]]
            return "\n".join(lines)

        # ── Git ──────────────────────────────────────────────────────────
        case "git_status":
            return toolbox.git_status()
        case "git_diff":
            return toolbox.git_diff(path=args.get("path", ""))
        case "git_log":
            return toolbox.git_log(max_commits=int(args.get("max_commits", 10)))
        case "git_commit":
            return toolbox.git_commit(
                message=args.get("message", ""),
                add_all=bool(args.get("add_all", True)),
            )

        # ── Progress tracking ─────────────────────────────────────────────────
        case "write_checkpoint":
            return toolbox.write_checkpoint(
                label=args.get("label", ""),
                content=args.get("content", ""),
            )
        case "read_checkpoint":
            return toolbox.read_checkpoint(label=args.get("label", ""))

        case _:
            return f"(unknown tool: {name})"


async def _dispatch_tool_async(toolbox: Toolbox, name: str, args: dict) -> str:
    """Async wrapper for tool dispatch.

    Most tools are synchronous; they run in a thread via asyncio.to_thread
    so they don't block the event loop.  Each call is bounded by _TOOL_TIMEOUT.

    spawn_worker is natively async (it runs a full child tool loop) and
    is dispatched directly without the thread wrapper.
    """
    # spawn_worker runs its own async tool loop — dispatch natively, not in a thread.
    if name == "spawn_worker":
        try:
            return await asyncio.wait_for(
                toolbox.spawn_worker(
                    task=args.get("task", ""),
                    label=args.get("label", ""),
                ),
                timeout=300,  # child agents can run up to 5 min
            )
        except asyncio.TimeoutError:
            return "(spawn_worker timed out after 300s)"
        except Exception as exc:
            log.error("spawn_worker raised: %s", exc)
            return f"(spawn_worker error: {exc})"

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_dispatch_tool, toolbox, name, args),
            timeout=_TOOL_TIMEOUT,
        )
        return result
    except asyncio.TimeoutError:
        log.error("Tool %s timed out after %ds", name, _TOOL_TIMEOUT)
        return f"(tool timed out after {_TOOL_TIMEOUT}s)"
    except Exception as exc:
        log.error("Tool %s raised: %s", name, exc)
        return f"(tool error: {exc})"


async def run_tool_loop(
    provider,  # Any provider that implements chat_with_tools
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
    called each time a tool is invoked (for status line updates in the TUI).
    """
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_message},
    ]

    for round_num in range(max_rounds):
        # Trim accumulated tool results before each LLM call to stay within
        # the context budget.  This must happen *before* the API call.
        messages = _trim_history(messages)

        log.debug("Tool loop round %d, messages=%d", round_num, len(messages))

        assistant_msg = await provider.chat_with_tools(
            messages=messages,
            tools=AGENT_TOOLS,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

        tool_calls = assistant_msg.get("tool_calls")
        content = assistant_msg.get("content", "")

        if not tool_calls:
            if content:
                yield content
            else:
                # Empty response with no tool calls — provider may be rate-limited
                # or returned a stop reason without content.  Stop the loop rather
                # than spinning.
                log.warning("Tool loop got empty response (no content, no tool calls) — stopping")
                yield "\n(agent stopped — model returned an empty response)\n"
            return

        # Yield any reasoning text the model produced *before* the tool calls
        # so the user sees the agent's thinking first, then the tool indicators.
        if content:
            yield content

        messages.append(assistant_msg)

        for tc in tool_calls:
            fn = tc["function"]
            name = fn["name"]
            try:
                args = json.loads(fn["arguments"])
            except (json.JSONDecodeError, TypeError):
                args = {}

            if on_tool_call:
                on_tool_call(name, args)

            log.info("Tool call: %s(%s)", name, json.dumps(args)[:200])
            yield f"\n`→ {name}({_brief_args(args)})`\n"

            result = await _dispatch_tool_async(toolbox, name, args)

            # Truncate huge results to keep the context window sane.
            # The agent can re-read specific ranges with start_line/end_line.
            if len(result) > 20_000:
                result = (
                    result[:20_000]
                    + f"\n... (truncated — {len(result):,} chars total; "
                    "use start_line/end_line to read specific sections)"
                )

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    yield "\n(reached max tool rounds — stopping)"


def _trim_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim old tool results when message history grows too large.

    Strategy:
      - Always keep the first message (the initial user query).
      - Prune the *content* of old ``role="tool"`` messages down to a one-line
        summary — they typically contain large file reads or command output that
        the model no longer needs verbatim.
      - Never remove assistant or user messages; their reasoning is load-bearing.
      - The last 4 messages are always kept intact (current round context).
    """
    total = sum(len(str(m.get("content", ""))) for m in messages)
    if total <= _HISTORY_CHAR_BUDGET:
        return messages

    keep_tail = 4  # always preserve the most recent messages in full
    cutoff = max(1, len(messages) - keep_tail)
    pruned = list(messages)
    for i in range(1, cutoff):
        m = pruned[i]
        if m.get("role") == "tool":
            content = str(m.get("content", ""))
            if len(content) > 300:
                first_line = content.splitlines()[0][:120] if content else ""
                pruned[i] = {
                    **m,
                    "content": (
                        f"[content pruned — was {len(content):,} chars; "
                        f"re-read with read_file if needed] {first_line}"
                    ),
                }
    log.debug(
        "History trimmed: was %d chars, now %d chars across %d messages",
        total,
        sum(len(str(m.get("content", ""))) for m in pruned),
        len(pruned),
    )
    return pruned


def _brief_args(args: dict) -> str:
    """Compact one-line representation of tool arguments for TUI display."""
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:57] + "..."
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)
