# Mission 08: Context Chunking and Retrieval

## Objective

Build a context chunking system that splits large files into semantically meaningful pieces, embeds them, and retrieves the most relevant chunks for a given query. This is the RAG (Retrieval-Augmented Generation) layer that lets Nala answer questions about large codebases without stuffing the entire project into the LLM context window.

## Why This Matters

Even the largest LLM context windows (200K tokens for Claude) cannot hold a real codebase. A 100K-line codebase is ~3.5M tokens — 17× too large. Without retrieval, Nala can only answer questions about code it has been explicitly shown. With retrieval, Nala can answer questions about any part of the codebase by fetching the most relevant chunks at query time.

This is the same architecture used by Cursor's codebase Q&A, GitHub Copilot Chat, and OpenCode's context system. The key insight is that *function-boundary chunking* (splitting at natural code boundaries rather than fixed token counts) produces dramatically better retrieval quality than sliding-window approaches.

## Context

The indexer already extracts symbols with line ranges. This mission uses those line ranges to create chunks, then stores embeddings in a vector store for retrieval. The chunking and embedding code lives in Python; the line range data comes from the Rust indexer via the IPC bridge.

## Implementation Steps

### Step 1: Design the chunk schema

A `Chunk` represents one unit of retrievable context:

```python
@dataclass
class Chunk:
    id: str               # sha256(file_path + str(start_line))
    file_path: str
    start_line: int
    end_line: int
    content: str          # raw source text of this chunk
    chunk_type: str       # "function", "class", "file_header", "block"
    symbol_name: str      # name if function/class, "" otherwise
    language: str
    token_estimate: int   # rough token count (len(content) // 4)
```

### Step 2: Build the ChunkSplitter (chunking/splitter.py)

Create `nala_orchestrator/chunking/splitter.py`.

Strategy (in priority order):
1. **Symbol-boundary chunks**: For each function/class symbol, create a chunk containing exactly that symbol's source lines. If the symbol > 300 lines, split into overlapping 250-line chunks with 50-line overlap.
2. **File-header chunk**: First 50 lines of every file (imports, module docstring, top-level constants) as a separate chunk.
3. **Gap-filling chunks**: Any contiguous region of source code not covered by a symbol chunk gets chunked at 200-line intervals.

Key methods:
- `split_file(file_path: str, symbols: list[Symbol]) -> list[Chunk]` — produces all chunks for one file
- `split_all(project_root: str, symbols: list[Symbol]) -> list[Chunk]` — processes entire project

### Step 3: Token estimation

Rather than invoking a tokeniser (which adds a heavy dependency), use a fast approximation: `token_estimate = len(content) // 4`. This is accurate to ±20% for English + code and avoids pulling in `tiktoken` or `sentencepiece`.

For the retrieval budget, use a conservative 4000-token limit per query (leaving room for conversation history and the response). This means at most ~16,000 characters of retrieved context.

### Step 4: Embedding and vector store (chunking/embedder.py)

Create `nala_orchestrator/chunking/embedder.py`.

**Embedding strategy:**
- If `ANTHROPIC_API_KEY` is set: use `voyage-code-2` via the Voyage AI API (best-in-class for code)
- If `OPENAI_API_KEY` is set: use `text-embedding-3-small`
- Fallback: BM25 keyword search (no embeddings required, good baseline)

**Vector store:**
Use `chromadb` (embedded, no server required) as the default vector store. Store at `{project_root}/.nala/vectors/`. On rebuild, delete and recreate.

Key methods:
- `embed_chunks(chunks: list[Chunk]) -> None` — compute and store embeddings
- `retrieve(query: str, top_k: int = 10) -> list[Chunk]` — return most relevant chunks
- `needs_rebuild(current_file_count: int) -> bool` — check if embeddings are stale

### Step 5: Context assembler (chunking/assembler.py)

Create `nala_orchestrator/chunking/assembler.py`. Given a list of retrieved chunks and a token budget, assemble a context string:

1. Deduplicate chunks (same file + overlapping lines → merge)
2. Sort by file path and line number (sequential reading is easier for the LLM)
3. Format each chunk with a header: `# {file_path}:{start_line}-{end_line} ({chunk_type})`
4. Trim to budget

### Step 6: Integration with AgentOrchestrator

Update `agents/orchestrator.py` to use retrieval before each query:

```python
async def stream_query(self, text: str) -> AsyncGenerator[str, None]:
    # Retrieve relevant chunks
    if self.embedder and self.embedder.is_ready():
        chunks = self.embedder.retrieve(text, top_k=10)
        context = self.assembler.assemble(chunks, token_budget=4000)
        system = self.SYSTEM_PROMPT_TEMPLATE.format(
            project_context=self.context_summary(),
            retrieved_context=context,
        )
    else:
        system = self.SYSTEM_PROMPT_TEMPLATE.format(
            project_context=self.context_summary(),
            retrieved_context="(vector store not available)",
        )
    # ... rest of query
```

### Step 7: Rebuild trigger

Add an `index_context` IPC handler (already in the protocol) that, after receiving updated file/symbol counts, triggers a background re-embed if the counts have changed significantly (> 5% change).

## Acceptance Criteria

- `ChunkSplitter.split_file()` produces non-overlapping chunks covering all code
- Chunks respect function boundaries (a function is never split mid-body unless it exceeds 300 lines)
- `Embedder.retrieve()` returns relevant results for code-related queries
- Context assembly stays within the token budget
- Embedding and retrieval work without a network connection (BM25 fallback)
- Rebuild is incremental: only re-embed chunks whose source has changed
- No file exceeds 400 lines

## Key Dependencies

- chromadb (local vector store)
- anthropic (voyage-code-2 embeddings) or openai (text-embedding-3-small)
- rank_bm25 (BM25 fallback)

## Estimated Complexity

High. The chunking strategy, embedding integration, and context assembly all have subtle correctness requirements. The BM25 fallback is important for making the system work without any API key.
