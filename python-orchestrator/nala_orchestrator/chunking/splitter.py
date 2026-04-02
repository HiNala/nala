"""Symbol-boundary chunk splitter.

Splits source files into semantically meaningful chunks aligned to function
and class boundaries extracted by the Rust indexer.  Never splits mid-function
(unless the function exceeds MAX_CHUNK_LINES).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

MAX_CHUNK_LINES = 300     # functions larger than this get split
CHUNK_OVERLAP   = 50      # overlap lines when splitting large functions
GAP_CHUNK_LINES = 200     # size of gap-filling chunks
HEADER_LINES    = 50      # lines to capture as the file-header chunk


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class Symbol:
    """Minimal symbol descriptor passed from the IPC bridge or indexer."""
    name: str
    kind: str           # "function" | "class" | "import" | ...
    start_line: int     # 1-based
    end_line: int       # 1-based, inclusive
    file_path: str


@dataclass
class Chunk:
    """One retrievable unit of source context."""
    id: str                 # sha256(file_path + ":" + str(start_line))
    file_path: str
    start_line: int         # 1-based
    end_line: int           # 1-based, inclusive
    content: str
    chunk_type: str         # "function" | "class" | "file_header" | "block"
    symbol_name: str        # name if function/class, "" otherwise
    language: str
    token_estimate: int     # len(content) // 4

    @staticmethod
    def make_id(file_path: str, start_line: int) -> str:
        key = f"{file_path}:{start_line}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


# ── Language detection ────────────────────────────────────────────────────────

_EXT_TO_LANG: dict[str, str] = {
    ".rs": "rust", ".py": "python", ".js": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".go": "go", ".java": "java", ".cpp": "cpp", ".c": "c",
    ".rb": "ruby", ".md": "markdown",
}


def _detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(ext, "text")


# ── ChunkSplitter ────────────────────────────────────────────────────────────

class ChunkSplitter:
    """Splits source files into chunks aligned to symbol boundaries."""

    def split_file(
        self,
        file_path: str,
        symbols: list[Symbol],
        source_lines: list[str] | None = None,
    ) -> list[Chunk]:
        """Return all chunks for one file.

        Args:
            file_path:    Absolute or relative path to the source file.
            symbols:      Symbols extracted by the indexer for this file.
            source_lines: Pre-read source lines (1-indexed via index+1).
                          If None, the file is read from disk.
        """
        if source_lines is None:
            try:
                with open(file_path, encoding="utf-8", errors="replace") as fh:
                    source_lines = fh.readlines()
            except OSError:
                return []

        total_lines = len(source_lines)
        if total_lines == 0:
            return []

        lang = _detect_language(file_path)
        chunks: list[Chunk] = []

        # Track which lines are covered by symbol chunks.
        covered: list[bool] = [False] * (total_lines + 1)  # 1-indexed

        # ── 1. Symbol-boundary chunks ─────────────────────────────────────
        file_syms = [s for s in symbols if s.file_path == file_path]
        for sym in file_syms:
            if sym.kind not in ("function", "class"):
                continue
            start = max(1, sym.start_line)
            end   = min(total_lines, sym.end_line)
            sym_lines = end - start + 1

            if sym_lines <= MAX_CHUNK_LINES:
                chunks.append(self._make_chunk(
                    file_path, start, end, source_lines, lang,
                    sym.kind, sym.name,
                ))
                for i in range(start, end + 1):
                    if i <= total_lines:
                        covered[i] = True
            else:
                # Split large symbol into overlapping sub-chunks.
                pos = start
                while pos <= end:
                    chunk_end = min(pos + MAX_CHUNK_LINES - 1, end)
                    chunks.append(self._make_chunk(
                        file_path, pos, chunk_end, source_lines, lang,
                        sym.kind, sym.name,
                    ))
                    for i in range(pos, chunk_end + 1):
                        if i <= total_lines:
                            covered[i] = True
                    pos = chunk_end - CHUNK_OVERLAP + 1

        # ── 2. File-header chunk ─────────────────────────────────────────
        header_end = min(HEADER_LINES, total_lines)
        chunks.append(self._make_chunk(
            file_path, 1, header_end, source_lines, lang,
            "file_header", "",
        ))
        for i in range(1, header_end + 1):
            covered[i] = True

        # ── 3. Gap-filling chunks ────────────────────────────────────────
        gap_start: int | None = None
        for i in range(1, total_lines + 1):
            if not covered[i]:
                if gap_start is None:
                    gap_start = i
            else:
                if gap_start is not None:
                    chunks.extend(self._gap_chunks(
                        file_path, gap_start, i - 1, source_lines, lang,
                    ))
                    gap_start = None
        if gap_start is not None:
            chunks.extend(self._gap_chunks(
                file_path, gap_start, total_lines, source_lines, lang,
            ))

        return chunks

    def split_all(
        self,
        project_root: str,
        symbols: list[Symbol],
    ) -> list[Chunk]:
        """Chunk all source files in the project."""
        # Group symbols by file for efficient lookup.
        by_file: dict[str, list[Symbol]] = {}
        for sym in symbols:
            by_file.setdefault(sym.file_path, []).append(sym)

        all_chunks: list[Chunk] = []
        for file_path, file_syms in by_file.items():
            all_chunks.extend(self.split_file(file_path, file_syms))

        return all_chunks

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_chunk(
        file_path: str,
        start: int,
        end: int,
        lines: list[str],
        lang: str,
        chunk_type: str,
        symbol_name: str,
    ) -> Chunk:
        content = "".join(lines[start - 1 : end])
        return Chunk(
            id=Chunk.make_id(file_path, start),
            file_path=file_path,
            start_line=start,
            end_line=end,
            content=content,
            chunk_type=chunk_type,
            symbol_name=symbol_name,
            language=lang,
            token_estimate=len(content) // 4,
        )

    @staticmethod
    def _gap_chunks(
        file_path: str,
        start: int,
        end: int,
        lines: list[str],
        lang: str,
    ) -> Iterator[Chunk]:
        pos = start
        while pos <= end:
            chunk_end = min(pos + GAP_CHUNK_LINES - 1, end)
            content = "".join(lines[pos - 1 : chunk_end])
            yield Chunk(
                id=Chunk.make_id(file_path, pos),
                file_path=file_path,
                start_line=pos,
                end_line=chunk_end,
                content=content,
                chunk_type="block",
                symbol_name="",
                language=lang,
                token_estimate=len(content) // 4,
            )
            pos = chunk_end + 1
