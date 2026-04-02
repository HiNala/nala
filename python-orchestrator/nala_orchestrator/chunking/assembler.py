"""Context assembler.

Given a list of retrieved chunks and a token budget, produces a formatted
context string for injection into an LLM prompt.

Assembly algorithm:
  1. Deduplicate / merge overlapping chunks from the same file.
  2. Sort by file path then start line (sequential reading aids comprehension).
  3. Format each chunk with a header comment showing location and type.
  4. Trim to the token budget, dropping lowest-ranked chunks first.
"""

from __future__ import annotations

from dataclasses import dataclass

from .splitter import Chunk

# Conservative token budget leaving room for conversation history + response.
DEFAULT_TOKEN_BUDGET = 4_000
# Approximate characters per token (code skews denser than prose).
CHARS_PER_TOKEN = 4


@dataclass
class AssembledContext:
    """Result of assembling retrieved chunks into a prompt-ready string."""
    text: str
    included_chunks: int
    total_chunks: int
    token_estimate: int


class ContextAssembler:
    """Assembles retrieved chunks into a single context string."""

    def assemble(
        self,
        chunks: list[Chunk],
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> AssembledContext:
        """Assemble chunks into a context string within the token budget.

        Args:
            chunks:       Chunks ordered by relevance (highest first).
            token_budget: Maximum tokens to include.

        Returns:
            An AssembledContext with the formatted text and metadata.
        """
        if not chunks:
            return AssembledContext(
                text="(no relevant context found)",
                included_chunks=0,
                total_chunks=0,
                token_estimate=0,
            )

        total = len(chunks)
        merged = self._merge_overlapping(chunks)
        sorted_chunks = sorted(merged, key=lambda c: (c.file_path, c.start_line))

        parts: list[str] = []
        tokens_used = 0

        for chunk in sorted_chunks:
            header = self._format_header(chunk)
            block = f"{header}\n{chunk.content}\n"
            block_tokens = len(block) // CHARS_PER_TOKEN
            if tokens_used + block_tokens > token_budget:
                break
            parts.append(block)
            tokens_used += block_tokens

        text = "\n".join(parts) if parts else "(context trimmed to fit budget)"
        return AssembledContext(
            text=text,
            included_chunks=len(parts),
            total_chunks=total,
            token_estimate=tokens_used,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _format_header(chunk: Chunk) -> str:
        label = chunk.symbol_name or chunk.chunk_type
        return (
            f"# {chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
            f" ({label}, {chunk.language})"
        )

    @staticmethod
    def _merge_overlapping(chunks: list[Chunk]) -> list[Chunk]:
        """Merge chunks from the same file whose line ranges overlap."""
        by_file: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            by_file.setdefault(chunk.file_path, []).append(chunk)

        merged: list[Chunk] = []
        for file_chunks in by_file.values():
            file_chunks.sort(key=lambda c: c.start_line)
            current = file_chunks[0]
            for nxt in file_chunks[1:]:
                if nxt.start_line <= current.end_line + 1:
                    # Extend the current chunk.
                    if nxt.end_line > current.end_line:
                        current = Chunk(
                            id=current.id,
                            file_path=current.file_path,
                            start_line=current.start_line,
                            end_line=nxt.end_line,
                            content=current.content,  # keep original; no double-read
                            chunk_type=current.chunk_type,
                            symbol_name=current.symbol_name,
                            language=current.language,
                            token_estimate=current.token_estimate + nxt.token_estimate,
                        )
                else:
                    merged.append(current)
                    current = nxt
            merged.append(current)

        return merged
