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

from .code_context import CodeCompressionResult, CodeContextCompressor
from .dedup import Deduplicator, DedupResult
from .facts import Fact, FactExtractor, FactSet
from .pipeline import CompressionPipeline, PipelineReport
from .quality import QualityChecker, QualityReport
from .structural import StructuralCompressor, StructuralResult
from .tool_outputs import ToolOutputResult, compress_tool_outputs, is_verbose_output

__all__ = [
    "CompressionPipeline", "PipelineReport",
    "Deduplicator", "DedupResult",
    "compress_tool_outputs", "is_verbose_output", "ToolOutputResult",
    "CodeContextCompressor", "CodeCompressionResult",
    "StructuralCompressor", "StructuralResult",
    "FactExtractor", "FactSet", "Fact",
    "QualityChecker", "QualityReport",
]
