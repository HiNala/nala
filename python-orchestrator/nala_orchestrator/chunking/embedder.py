"""Chunk embedder and retriever using BM25 + optional vector store.

Strategy (in order of preference):
  1. OpenAI text-embedding-3-small  (if OPENAI_API_KEY is set)
  2. Voyage voyage-code-2           (if ANTHROPIC_API_KEY is set, via Voyage)
  3. BM25 keyword search            (always available, no network required)

ChromaDB is used as the embedded vector store when embeddings are available.
BM25 runs fully in-process from rank_bm25.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .splitter import Chunk

log = logging.getLogger(__name__)

_DEFAULT_TOP_K = 20
_CHROMA_COLLECTION = "nala_chunks"


class _BM25Backend:
    """Pure-Python BM25 retrieval. Falls back to keyword overlap if rank_bm25
    is not installed."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._bm25 = None

    def build(self, chunks: list[Chunk]) -> None:
        try:
            from rank_bm25 import BM25Okapi  # type: ignore
        except ImportError:
            log.warning("rank_bm25 not installed — keyword retrieval degraded. "
                        "pip install rank-bm25")
            self._chunks = chunks
            return
        self._chunks = chunks
        self._bm25 = BM25Okapi([self._tok(c.content) for c in chunks])

    def retrieve(self, query: str, top_k: int = _DEFAULT_TOP_K) -> list[Chunk]:
        if not self._chunks:
            return []
        if self._bm25 is None:
            return self._fallback(query, top_k)
        scores = self._bm25.get_scores(self._tok(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._chunks[i] for i in ranked[:top_k]]

    @staticmethod
    def _tok(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())

    def _fallback(self, query: str, top_k: int) -> list[Chunk]:
        tokens = set(self._tok(query))
        scored = [(len(tokens & set(self._tok(c.content))), c) for c in self._chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def is_ready(self) -> bool:
        return bool(self._chunks)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


class Embedder:
    """Manages chunk storage and retrieval for one project.

    Always initialises with BM25.  If a supported embedding API key is present
    and chromadb is installed, also builds a persistent vector index under
    .nala/vectors/.
    """

    def __init__(self, project_root: str) -> None:
        self._root = Path(project_root)
        self._store_dir = self._root / ".nala" / "vectors"
        self._bm25 = _BM25Backend()
        self._chroma_collection = None
        self._embed_fn = None
        self._chunks: list[Chunk] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self, chunks: list[Chunk], source_file_count: int = 0) -> None:
        """Index all chunks. Call after a scan/index completes."""
        self._chunks = chunks
        self._source_file_count = source_file_count
        self._bm25.build(chunks)
        self._try_build_vector_index(chunks)
        log.info("Embedder indexed %d chunks from %d files (vector=%s)",
                 len(chunks), source_file_count, self._chroma_collection is not None)

    def retrieve(self, query: str, top_k: int = _DEFAULT_TOP_K) -> list[Chunk]:
        """Return the top-k most relevant chunks for a query."""
        if self._chroma_collection is not None:
            try:
                return self._vector_retrieve(query, top_k)
            except Exception as exc:
                log.debug("Vector retrieval failed, BM25 fallback: %s", exc)
        return self._bm25.retrieve(query, top_k)

    def needs_rebuild(self, current_file_count: int) -> bool:
        """True if the index should be rebuilt."""
        if not self._chunks:
            return True
        if not hasattr(self, "_source_file_count") or self._source_file_count == 0:
            return True
        ratio = abs(current_file_count - self._source_file_count) / max(1, self._source_file_count)
        return ratio > 0.05

    def is_ready(self) -> bool:
        return self._bm25.is_ready()

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _try_build_vector_index(self, chunks: list[Chunk]) -> None:
        embed_fn = self._detect_embed_fn()
        if embed_fn is None:
            return
        try:
            import chromadb  # type: ignore
        except ImportError:
            log.debug("chromadb not installed — using BM25 only")
            return
        try:
            self._store_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self._store_dir))
            try:
                client.delete_collection(_CHROMA_COLLECTION)
            except Exception:
                pass
            col = client.create_collection(_CHROMA_COLLECTION)
            for i in range(0, len(chunks), 50):
                batch = chunks[i : i + 50]
                texts = [c.content[:4000] for c in batch]
                col.add(
                    ids=[c.id for c in batch],
                    embeddings=embed_fn(texts),
                    documents=texts,
                    metadatas=[{
                        "file_path": c.file_path, "start_line": c.start_line,
                        "end_line": c.end_line, "chunk_type": c.chunk_type,
                        "symbol_name": c.symbol_name, "language": c.language,
                    } for c in batch],
                )
            self._chroma_collection = col
        except Exception as exc:
            log.warning("Vector index build failed: %s — using BM25", exc)
            self._chroma_collection = None

    def _vector_retrieve(self, query: str, top_k: int) -> list[Chunk]:
        if self._chroma_collection is None:
            return self._bm25.retrieve(query, top_k)
        embed_fn = self._detect_embed_fn()
        if embed_fn is None:
            return self._bm25.retrieve(query, top_k)
        q_embed = embed_fn([query])
        results = self._chroma_collection.query(
            query_embeddings=q_embed,
            n_results=min(top_k, self._chroma_collection.count()),
        )
        id_set = {c.id: c for c in self._chunks}
        return [id_set[cid] for cid in results.get("ids", [[]])[0] if cid in id_set]

    def _detect_embed_fn(self):
        if self._embed_fn is not None:
            return self._embed_fn
        for env_var, factory in [
            ("OPENAI_API_KEY", self._make_openai_embed),
            ("ANTHROPIC_API_KEY", self._make_voyage_embed),
        ]:
            key = os.getenv(env_var)
            if key:
                fn = factory(key)
                if fn:
                    self._embed_fn = fn
                    return fn
        return None

    @staticmethod
    def _make_openai_embed(api_key: str):
        try:
            import openai  # type: ignore
            client = openai.OpenAI(api_key=api_key)

            def embed(texts: list[str]) -> list[list[float]]:
                resp = client.embeddings.create(
                    model="text-embedding-3-small", input=texts
                )
                return [item.embedding for item in resp.data]

            return embed
        except Exception as exc:
            log.debug("OpenAI embed setup failed: %s", exc)
            return None

    @staticmethod
    def _make_voyage_embed(api_key: str):
        try:
            import voyageai  # type: ignore
            vc = voyageai.Client(api_key=api_key)

            def embed(texts: list[str]) -> list[list[float]]:
                return vc.embed(texts, model="voyage-code-2").embeddings

            return embed
        except Exception as exc:
            log.debug("Voyage embed setup failed: %s", exc)
            return None
