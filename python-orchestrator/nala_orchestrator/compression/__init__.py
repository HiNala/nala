"""Context compression pipeline.

Provides multi-stage, quality-gated compression for conversation history
and individual text blocks. Reduces context by 40-70% while preserving
all factual identifiers (paths, symbols, line numbers).

Architecture:
  CompressionPipeline  — top-level orchestrator
  Deduplicator         — remove near-duplicate paragraph blocks
  ToolOutputCompressor — compress verbose code/JSON outputs
  CodeContextCompressor— preserve code signatures, compress bodies
  StructuralCompressor — Markdown-aware prose compression
  FactExtractor        — audit / extract factual identifiers
  QualityChecker       — validate compression safety invariants
"""

from .pipeline import CompressionPipeline, PipelineReport
from .dedup import Deduplicator, DedupResult
from .tool_outputs import compress_tool_outputs, is_verbose_output, ToolOutputResult
from .code_context import CodeContextCompressor, CodeCompressionResult
from .structural import StructuralCompressor, StructuralResult
from .facts import FactExtractor, FactSet, Fact
from .quality import QualityChecker, QualityReport

__all__ = [
    "CompressionPipeline", "PipelineReport",
    "Deduplicator", "DedupResult",
    "compress_tool_outputs", "is_verbose_output", "ToolOutputResult",
    "CodeContextCompressor", "CodeCompressionResult",
    "StructuralCompressor", "StructuralResult",
    "FactExtractor", "FactSet", "Fact",
    "QualityChecker", "QualityReport",
]
