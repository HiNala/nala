"""Structural (Markdown-aware) compressor.

Compresses text while preserving its structural skeleton:
  - Headings (# / ## / ###) — kept verbatim
  - Bullet lists — each item compressed individually
  - Numbered lists — items compressed, numbers kept
  - Code fences — kept verbatim (code_context.py handles those separately)
  - Paragraphs — compressed with SmartStrip sentence classifier

This ensures that compacted responses still look well-structured when
injected back as system context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class StructuralResult:
    """Metrics from one structural compression pass."""
    original_chars: int
    compressed_chars: int
    blocks_processed: int

    @property
    def reduction_pct(self) -> float:
        if self.original_chars == 0:
            return 0.0
        return (1.0 - self.compressed_chars / self.original_chars) * 100


class StructuralCompressor:
    """Preserves Markdown structure while compressing prose content."""

    def compress(self, text: str) -> tuple[str, StructuralResult]:
        """Return (compressed_text, metrics)."""
        from ..memory.compression import SmartStrip
        ss = SmartStrip()
        blocks = self._split_blocks(text)
        out: list[str] = []
        processed = 0

        for kind, content in blocks:
            if kind == "heading":
                out.append(content)
            elif kind == "code":
                out.append(content)  # code blocks handled by code_context
            elif kind == "bullets":
                out.append(self._compress_list(content, ss))
                processed += 1
            elif kind == "numbered":
                out.append(self._compress_numbered(content, ss))
                processed += 1
            elif kind == "paragraph":
                compressed = _safe_compress_paragraph(content, ss)
                if compressed:
                    out.append(compressed)
                processed += 1
            else:
                out.append(content)

        result_text = "\n\n".join(b for b in out if b.strip())
        return result_text, StructuralResult(
            original_chars=len(text),
            compressed_chars=len(result_text),
            blocks_processed=processed,
        )

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _split_blocks(text: str) -> list[tuple[str, str]]:
        """Split text into (kind, content) tuples."""
        blocks: list[tuple[str, str]] = []
        current: list[str] = []
        in_code = False
        code_fence: list[str] = []

        for line in text.splitlines():
            if line.startswith("```"):
                if in_code:
                    code_fence.append(line)
                    blocks.append(("code", "\n".join(code_fence)))
                    code_fence = []
                    in_code = False
                else:
                    if current:
                        blocks.extend(_classify_block("\n".join(current)))
                        current = []
                    in_code = True
                    code_fence = [line]
                continue

            if in_code:
                code_fence.append(line)
                continue

            if not line.strip():
                if current:
                    blocks.extend(_classify_block("\n".join(current)))
                    current = []
            else:
                current.append(line)

        if in_code and code_fence:
            blocks.append(("code", "\n".join(code_fence)))
        elif current:
            blocks.extend(_classify_block("\n".join(current)))

        return blocks

    @staticmethod
    def _compress_list(content: str, ss) -> str:
        from ..memory.compression import _IDENTIFIER_RE, _classify, _strip_hedges
        lines = content.splitlines()
        out: list[str] = []
        for line in lines:
            prefix = ""
            body = line
            for pfx in ("  - ", "  * ", "- ", "* ", "• "):
                if line.startswith(pfx):
                    prefix, body = pfx, line[len(pfx):]
                    break
            # Never drop lines that contain identifiers (paths/symbols)
            if _classify(body) == "filler" and not _IDENTIFIER_RE.search(body):
                continue
            out.append(prefix + _strip_hedges(body))
        return "\n".join(out)

    @staticmethod
    def _compress_numbered(content: str, ss) -> str:
        from ..memory.compression import _IDENTIFIER_RE, _classify, _strip_hedges
        lines = content.splitlines()
        out: list[str] = []
        for line in lines:
            m = re.match(r"^(\d+\.\s+)(.*)", line)
            if m:
                num_prefix, body = m.group(1), m.group(2)
                if _classify(body) == "filler" and not _IDENTIFIER_RE.search(body):
                    continue
                out.append(num_prefix + _strip_hedges(body))
            else:
                out.append(line)
        return "\n".join(out)


def _safe_compress_paragraph(text: str, ss) -> str:
    """Compress a paragraph but never discard sentences with identifiers."""
    from ..memory.compression import _IDENTIFIER_RE, _classify, _split_sentences, _strip_hedges
    sentences = _split_sentences(text)
    kept: list[str] = []
    for sent in sentences:
        cat = _classify(sent)
        if cat == "filler" and not _IDENTIFIER_RE.search(sent):
            continue
        kept.append(_strip_hedges(sent))
    return " ".join(s for s in kept if s.strip())


def _classify_block(text: str) -> list[tuple[str, str]]:
    """Classify a block of text into (kind, content) pairs."""
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("#"):
        return [("heading", stripped)]
    lines = stripped.splitlines()
    if all(re.match(r"^[-*•]\s", ln.lstrip()) or not ln.strip() for ln in lines):
        return [("bullets", stripped)]
    if all(re.match(r"^\d+\.\s", ln) or not ln.strip() for ln in lines):
        return [("numbered", stripped)]
    return [("paragraph", stripped)]
