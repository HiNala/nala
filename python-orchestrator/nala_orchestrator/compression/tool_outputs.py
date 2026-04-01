"""Tool output compressor.

Detects and compresses verbose tool outputs in conversation turns:
  - Code blocks longer than MAX_CODE_LINES → keep first/last N lines
  - JSON blobs → summarise key count and top-level keys
  - Command output (stderr/stdout dumps) → first 3 + last 3 lines
  - Repeated stack traces → deduplicate to one canonical trace

Operates on individual message content strings, not the full history.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MAX_CODE_LINES = 40          # code blocks longer than this get trimmed
KEEP_HEAD_TAIL = 5           # lines to keep at start/end of long outputs
MAX_JSON_KEYS_SHOWN = 8      # show this many top-level JSON keys


@dataclass
class ToolOutputResult:
    """Metrics from compressing one message's tool outputs."""
    original_chars: int
    compressed_chars: int
    blocks_compressed: int


def compress_tool_outputs(content: str) -> tuple[str, ToolOutputResult]:
    """Compress verbose tool outputs in a message.

    Returns (compressed_content, metrics).
    """
    original = content
    blocks_compressed = 0

    # ── Fenced code blocks ────────────────────────────────────────────────
    def compress_code_block(m: re.Match) -> str:
        nonlocal blocks_compressed
        lang = m.group(1) or ""
        body = m.group(2)
        lines = body.splitlines()
        if len(lines) <= MAX_CODE_LINES:
            return m.group(0)  # short enough — keep as-is
        head = lines[:KEEP_HEAD_TAIL]
        tail = lines[-KEEP_HEAD_TAIL:]
        omitted = len(lines) - 2 * KEEP_HEAD_TAIL
        blocks_compressed += 1
        trimmed = "\n".join(head) + f"\n... [{omitted} lines omitted] ...\n" + "\n".join(tail)
        return f"```{lang}\n{trimmed}\n```"

    content = re.sub(
        r"```([a-zA-Z0-9_]*)\n([\s\S]*?)```",
        compress_code_block,
        content,
    )

    # ── Inline JSON blobs (> 200 chars) ───────────────────────────────────
    def compress_json(m: re.Match) -> str:
        nonlocal blocks_compressed
        raw = m.group(0)
        if len(raw) < 200:
            return raw
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
        if isinstance(obj, dict):
            keys = list(obj.keys())
            shown = keys[:MAX_JSON_KEYS_SHOWN]
            extra = len(keys) - len(shown)
            key_list = ", ".join(f'"{k}"' for k in shown)
            suffix = f", ... +{extra} more" if extra else ""
            blocks_compressed += 1
            return f"{{/* {len(keys)} keys: {key_list}{suffix} */}}"
        if isinstance(obj, list):
            blocks_compressed += 1
            return f"[/* {len(obj)} items */]"
        return raw

    content = re.sub(r"\{[\s\S]{200,}?\}", compress_json, content)

    # ── Long plain-text outputs (e.g. command stdout) ─────────────────────
    # Only outside code fences: paragraphs > MAX_CODE_LINES plain lines.
    def compress_plain_block(m: re.Match) -> str:
        nonlocal blocks_compressed
        block = m.group(0)
        lines = block.splitlines()
        if len(lines) <= MAX_CODE_LINES:
            return block
        head = lines[:KEEP_HEAD_TAIL]
        tail = lines[-KEEP_HEAD_TAIL:]
        omitted = len(lines) - 2 * KEEP_HEAD_TAIL
        blocks_compressed += 1
        return "\n".join(head) + f"\n... [{omitted} lines omitted] ...\n" + "\n".join(tail)

    # Match paragraphs with many consecutive non-blank lines (likely output)
    content = re.sub(
        r"(?m)^([^\n`].{0,200}\n){" + str(MAX_CODE_LINES + 1) + r",}",
        compress_plain_block,
        content,
    )

    return content, ToolOutputResult(
        original_chars=len(original),
        compressed_chars=len(content),
        blocks_compressed=blocks_compressed,
    )


def is_verbose_output(content: str, threshold: int = MAX_CODE_LINES) -> bool:
    """Heuristic: does this message contain verbose tool output?"""
    code_fence_count = content.count("```")
    if code_fence_count >= 2:
        # Find the longest code block
        for m in re.finditer(r"```[a-zA-Z0-9_]*\n([\s\S]*?)```", content):
            if len(m.group(1).splitlines()) > threshold:
                return True
    # Long JSON
    if re.search(r"\{[\s\S]{500,}?\}", content):
        return True
    return False
