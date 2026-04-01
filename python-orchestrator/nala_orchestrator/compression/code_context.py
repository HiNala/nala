"""Code-context-aware compressor.

When a conversation turn contains source code, this compressor:
  1. Preserves function/class signatures verbatim.
  2. Compresses function bodies to a 1-line summary if body > BODY_THRESHOLD lines.
  3. Keeps all import statements.
  4. Strips blank lines inside function bodies (not between definitions).

Operates on fenced code blocks (``` ... ```) inside message content.
Plain code is left unchanged — use tool_outputs.py for that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


BODY_THRESHOLD = 15  # lines — bodies longer than this are summarised


@dataclass
class CodeCompressionResult:
    """Metrics from compressing code blocks."""
    blocks_found: int
    blocks_compressed: int
    lines_saved: int


class CodeContextCompressor:
    """Compresses source code inside fenced Markdown code blocks."""

    def compress(self, content: str) -> tuple[str, CodeCompressionResult]:
        """Compress code blocks in a message content string."""
        blocks_found = 0
        blocks_compressed = 0
        lines_saved = 0

        def replace_block(m: re.Match) -> str:
            nonlocal blocks_found, blocks_compressed, lines_saved
            lang = m.group(1) or ""
            body = m.group(2)
            blocks_found += 1

            if lang not in ("python", "py", "rust", "rs", "go", "ts", "js",
                            "typescript", "javascript", "java", "cpp", "c"):
                return m.group(0)  # skip non-code blocks

            compressed, saved = _compress_code_body(body, lang)
            if saved > 0:
                blocks_compressed += 1
                lines_saved += saved
                return f"```{lang}\n{compressed}\n```"
            return m.group(0)

        result = re.sub(
            r"```([a-zA-Z0-9_]*)\n([\s\S]*?)```",
            replace_block,
            content,
        )
        return result, CodeCompressionResult(
            blocks_found=blocks_found,
            blocks_compressed=blocks_compressed,
            lines_saved=lines_saved,
        )


def _compress_code_body(code: str, lang: str) -> tuple[str, int]:
    """Compress a code body. Returns (compressed, lines_saved)."""
    lines = code.splitlines()
    if len(lines) <= BODY_THRESHOLD:
        return code, 0

    lang_lower = lang.lower()
    if lang_lower in ("python", "py"):
        return _compress_python(lines)
    if lang_lower in ("rust", "rs"):
        return _compress_rust(lines)
    # Generic fallback
    return _compress_generic(lines)


def _compress_python(lines: list[str]) -> tuple[str, int]:
    """Compress Python: keep defs, classes, imports; summarise bodies."""
    out: list[str] = []
    i = 0
    original_len = len(lines)

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Keep imports, class/function defs, decorators, blank lines between blocks
        if (stripped.startswith(("import ", "from ", "class ", "def ", "@"))
                or stripped.startswith("#")
                or not stripped):
            out.append(line)
            i += 1
            continue

        # If this is a body line, consume until next def/class/blank
        body: list[str] = []
        while i < len(lines):
            l = lines[i]
            s = l.strip()
            if s.startswith(("def ", "class ", "@", "import ", "from ")):
                break
            if not s and body:  # blank line after body
                break
            body.append(l)
            i += 1

        if len(body) > 4:
            out.append(f"    # ... [{len(body)} lines] ...")
        else:
            out.extend(body)

    compressed = "\n".join(out)
    return compressed, original_len - len(out)


def _compress_rust(lines: list[str]) -> tuple[str, int]:
    """Compress Rust: keep fn/struct/impl/use; summarise bodies."""
    out: list[str] = []
    i = 0
    original_len = len(lines)
    brace_depth = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        opens = line.count("{")
        closes = line.count("}")

        # Signature lines
        if (stripped.startswith(("fn ", "pub fn", "async fn", "pub async",
                                  "struct ", "impl ", "use ", "mod ", "//", "#["))
                or stripped in ("{", "}", "};", "},")):
            out.append(line)
            brace_depth += opens - closes
            i += 1
            continue

        # Body accumulation when inside braces
        if brace_depth > 0:
            body: list[str] = []
            depth = brace_depth
            while i < len(lines):
                l = lines[i]
                s = l.strip()
                o, c = l.count("{"), l.count("}")
                body.append(l)
                depth += o - c
                i += 1
                if depth <= 1 and (s == "}" or s == "};"):
                    break

            if len(body) > 5:
                indent = "    "
                out.append(f"{indent}// ... [{len(body)} lines] ...")
                if body and (body[-1].strip() in ("}", "};")):
                    out.append(body[-1])
            else:
                out.extend(body)
            brace_depth = depth
            continue

        out.append(line)
        brace_depth += opens - closes
        i += 1

    compressed = "\n".join(out)
    return compressed, original_len - len(out)


def _compress_generic(lines: list[str]) -> tuple[str, int]:
    """Generic: keep first BODY_THRESHOLD lines + count omitted."""
    kept = lines[:BODY_THRESHOLD]
    omitted = len(lines) - BODY_THRESHOLD
    if omitted > 0:
        kept.append(f"// ... [{omitted} more lines] ...")
    return "\n".join(kept), omitted
