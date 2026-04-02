"""Context compression pipeline.

Orchestrates all compression stages in a fixed order, with per-stage
quality gating. Each stage is optional and can be skipped individually.

Stage order (highest savings first, lowest information risk first):
  1. Dedup           — remove near-duplicate blocks (0-risk)
  2. Tool outputs    — compress verbose code/JSON outputs
  3. Code context    — compress code bodies in fenced blocks
  4. Structural      — Markdown-aware prose compression
  5. Facts audit     — verify no factual identifiers were lost

Usage:
    pipeline = CompressionPipeline()
    new_history, report = pipeline.compress_history(history)

    # Or compress a single string:
    compressed, report = pipeline.compress_text(text)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .code_context import CodeContextCompressor
from .dedup import Deduplicator
from .facts import FactExtractor
from .quality import QualityChecker, QualityReport
from .structural import StructuralCompressor
from .tool_outputs import compress_tool_outputs, is_verbose_output

log = logging.getLogger(__name__)


@dataclass
class PipelineReport:
    """Aggregated metrics across all compression stages."""
    original_chars: int
    final_chars: int
    original_turns: int
    final_turns: int
    dedup_removed: int
    tool_blocks_compressed: int
    code_blocks_compressed: int
    structural_blocks: int
    quality: QualityReport | None = None
    stages_applied: list[str] = field(default_factory=list)

    @property
    def reduction_pct(self) -> float:
        if self.original_chars == 0:
            return 0.0
        return (1.0 - self.final_chars / self.original_chars) * 100

    def summary(self) -> str:
        lines = [
            f"Compression pipeline: {self.reduction_pct:.0f}% reduction "
            f"({self.original_chars:,} -> {self.final_chars:,} chars)",
            f"  Stages: {', '.join(self.stages_applied) or 'none'}",
            f"  Dedup: {self.dedup_removed} duplicates removed",
            f"  Tool outputs: {self.tool_blocks_compressed} blocks compressed",
            f"  Code context: {self.code_blocks_compressed} blocks compressed",
        ]
        if self.quality:
            lines.append(f"  {self.quality.summary()}")
        return "\n".join(lines)


class CompressionPipeline:
    """Full context compression pipeline."""

    def __init__(
        self,
        enable_dedup: bool = True,
        enable_tool_outputs: bool = True,
        enable_code_context: bool = True,
        enable_structural: bool = True,
        enable_quality_check: bool = True,
    ) -> None:
        self._dedup = Deduplicator() if enable_dedup else None
        self._code = CodeContextCompressor() if enable_code_context else None
        self._structural = StructuralCompressor() if enable_structural else None
        self._facts = FactExtractor()
        self._quality = QualityChecker() if enable_quality_check else None
        self._enable_tool = enable_tool_outputs

    # ── Public API ────────────────────────────────────────────────────────────

    def compress_history(
        self,
        history: list[dict],
        keep_recent: int = 5,
    ) -> tuple[list[dict], PipelineReport]:
        """Compress a conversation history list.

        Keeps the most recent `keep_recent` turns verbatim.
        Compresses older turns through the full pipeline.

        Returns (new_history, report).
        """
        if len(history) <= keep_recent:
            orig_chars = sum(len(m.get("content", "")) for m in history)
            return history, PipelineReport(
                original_chars=orig_chars, final_chars=orig_chars,
                original_turns=len(history), final_turns=len(history),
                dedup_removed=0, tool_blocks_compressed=0,
                code_blocks_compressed=0, structural_blocks=0,
            )

        old = history[: len(history) - keep_recent]
        recent = history[len(history) - keep_recent :]

        # Stage 0: dedup assistant turns in older history
        dedup_removed = 0
        if self._dedup:
            old, dedup_removed = self._dedup.deduplicate_history(old)

        # Stage 1-4: compress each old turn individually
        tool_total = 0
        code_total = 0
        struct_total = 0
        stages: set[str] = set()

        compressed_old: list[dict] = []
        for msg in old:
            content = msg.get("content", "")
            if not content or msg.get("role") == "system":
                compressed_old.append(msg)
                continue

            new_content, tc, cc, sc, applied = self._compress_content(content)
            tool_total += tc
            code_total += cc
            struct_total += sc
            stages.update(applied)
            compressed_old.append({**msg, "content": new_content})

        new_history = compressed_old + recent

        orig_chars = sum(len(m.get("content", "")) for m in history)
        final_chars = sum(len(m.get("content", "")) for m in new_history)

        quality: QualityReport | None = None
        if self._quality:
            orig_text = " ".join(m.get("content", "") for m in old)
            comp_text = " ".join(m.get("content", "") for m in compressed_old)
            quality = self._quality.check(orig_text, comp_text)
            if not quality.passed:
                log.warning("Compression quality check failed: %s", quality.summary())

        if dedup_removed:
            stages.add("dedup")

        return new_history, PipelineReport(
            original_chars=orig_chars,
            final_chars=final_chars,
            original_turns=len(history),
            final_turns=len(new_history),
            dedup_removed=dedup_removed,
            tool_blocks_compressed=tool_total,
            code_blocks_compressed=code_total,
            structural_blocks=struct_total,
            quality=quality,
            stages_applied=sorted(stages),
        )

    def compress_text(self, text: str) -> tuple[str, PipelineReport]:
        """Compress a single text block through all enabled stages."""
        content, tc, cc, sc, stages = self._compress_content(text)
        orig_chars = len(text)
        final_chars = len(content)
        quality: QualityReport | None = None
        if self._quality:
            quality = self._quality.check(text, content)
            if not quality.passed:
                content = text  # fall back to original
                final_chars = orig_chars
        return content, PipelineReport(
            original_chars=orig_chars,
            final_chars=final_chars,
            original_turns=1,
            final_turns=1,
            dedup_removed=0,
            tool_blocks_compressed=tc,
            code_blocks_compressed=cc,
            structural_blocks=sc,
            quality=quality,
            stages_applied=sorted(stages),
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _compress_content(
        self, content: str
    ) -> tuple[str, int, int, int, set[str]]:
        """Run content through all stages. Returns (text, tool_n, code_n, struct_n, stages)."""
        tc = cc = sc = 0
        stages: set[str] = set()

        # Tool outputs first (highest savings, lowest loss)
        if self._enable_tool and is_verbose_output(content):
            content, result = compress_tool_outputs(content)
            if result.blocks_compressed:
                tc = result.blocks_compressed
                stages.add("tool_outputs")

        # Code context (keeps signatures, trims bodies)
        if self._code:
            content, cr = self._code.compress(content)
            if cr.blocks_compressed:
                cc = cr.blocks_compressed
                stages.add("code_context")

        # Structural prose compression (last — least aggressive)
        if self._structural:
            content, sr = self._structural.compress(content)
            if sr.blocks_processed:
                sc = sr.blocks_processed
                stages.add("structural")

        return content, tc, cc, sc, stages
