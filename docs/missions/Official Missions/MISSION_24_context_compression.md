# Mission 24: Context Compression and Smart Summarization

## Objective

Build the context compression pipeline that reduces codebase context, conversation history, and tool outputs to their essential information while preserving every fact that matters. This is the engine that makes Missions 20-23 work efficiently. Without good compression, memory systems waste tokens on fluff and agents lose critical details. With good compression, Nala fits 3x more useful context into the same token budget.

## Why This Matters

The research is unambiguous: curation beats volume. A model with 50,000 tokens of well-curated context outperforms the same model with 150,000 tokens of raw, unfiltered context. The "lost in the middle" problem means that information buried in the middle of long contexts is effectively invisible to the model, even if it is technically within the window. And every unnecessary token costs money, adds latency, and dilutes the signal the model uses to reason.

Erold's Smart Strip technique achieves 2-3x compression while surviving unlimited re-compression cycles without drift. Anthropic's own research shows that tool output pruning alone can recover 30-50% of consumed tokens. The Zylos Research report found that embedding-based compression achieves 80-90% token reduction for stored history. Nala combines the best of these approaches into a unified compression pipeline.

## Implementation Steps

### Step 1: Compression pipeline architecture (compression/pipeline.py)

Build a `CompressionPipeline` that chains multiple compression stages. Each stage takes text and returns compressed text. Stages can be enabled or disabled based on the content type.

```python
class CompressionPipeline:
    def compress(self, content: str, content_type: str, 
                 target_ratio: float = 0.4) -> CompressedContent:
        """
        Compress content to approximately target_ratio of original size.
        content_type: "conversation" | "tool_output" | "code" | "analysis" | "memory"
        target_ratio: 0.4 means reduce to 40% of original (60% reduction)
        """
```

The pipeline applies stages in order, checking after each stage whether the target ratio has been reached. If it has, stop early (do not over-compress).

### Step 2: Stage 1 -- Structural stripping (compression/structural.py)

Remove structural noise that adds no informational value:
- Strip markdown formatting characters (##, **, ```) while preserving the text
- Remove blank lines (compress to single line breaks)
- Remove common filler phrases: "Let me explain...", "Here's what I found...", "As you can see...", "In summary...", "To clarify..."
- Remove self-referential meta-commentary: "I'll now analyze...", "Let me search for...", "Based on what you told me..."
- Collapse repeated whitespace
- Remove ASCII art, decorative borders, and separator lines

This stage typically achieves 15-25% reduction with zero information loss.

### Step 3: Stage 2 -- Tool output compression (compression/tool_outputs.py)

Tool outputs (file contents, grep results, test output, compiler errors) are the biggest token consumers and the most compressible:

**File content compression**: When a file was read but only a few functions were relevant, replace the full file content with the relevant functions plus a one-line summary of what else was in the file.

**Grep/search result compression**: Replace verbose search output with a compact table: file path, line number, matching text (truncated to 80 chars).

**Test output compression**: Replace full test runner output with: X passed, Y failed, Z skipped. For failures, keep only the assertion message and file/line, not the full stack trace.

**Compiler/linter output compression**: Keep only errors and warnings with file/line. Remove notes, suggestions, and help text.

This stage typically achieves 40-60% reduction on tool-heavy conversations.

### Step 4: Stage 3 -- Fact extraction (compression/facts.py)

This is the core intelligence of the compression system. It extracts structured facts from free-form text.

Implement the Smart Strip algorithm:
1. Parse the text into sentences
2. For each sentence, classify it:
   - **Fact**: Contains a verifiable claim (file path, function name, metric value, decision, constraint). Keep it, compress it.
   - **Reasoning**: Explains why something is the case. Keep if it supports a key decision, otherwise discard.
   - **Filler**: Conversational text with no informational content. Discard entirely.
   - **Action**: Describes something that was done or needs to be done. Keep it.
3. For kept sentences, compress them:
   - Remove unnecessary words while preserving meaning
   - Replace verbose descriptions with terse equivalents
   - Preserve all proper nouns, file paths, function names, numbers, and code identifiers exactly

Example input (187 tokens):
```
I looked at the process_payment function in src/billing/processor.rs and found that 
it has a cyclomatic complexity of 28, which is significantly above our threshold of 
10. The main issue is a deeply nested chain of if-else statements that handle 
different payment methods (credit card, bank transfer, crypto, and gift cards). I 
think the best approach would be to use a strategy pattern to extract each payment 
method into its own handler function. This would reduce the complexity of the main 
function to around 5-6 and make each handler independently testable.
```

Example output (62 tokens):
```
src/billing/processor.rs: process_payment() CC=28 (threshold: 10). Cause: nested 
if-else for payment methods (credit card, bank transfer, crypto, gift cards). 
Fix: strategy pattern, extract per-method handlers. Expected result: CC ~5-6, 
independently testable.
```

67% reduction, zero fact loss.

### Step 5: Stage 4 -- Semantic deduplication (compression/dedup.py)

Across a conversation, the same fact is often stated multiple times in different ways. Detect and merge duplicates:

1. Extract key entities from each compressed fact (file paths, function names, metric values)
2. Group facts by shared entities
3. Within each group, merge facts that say the same thing (keep the most complete version)
4. Preserve contradictions (if a fact changed, keep both with timestamps)

### Step 6: Stage 5 -- Code context compression (compression/code_context.py)

When injecting codebase context (file contents, function signatures, symbol graphs), compress it specifically for code:

**Signature-only mode**: For functions that are referenced but not being modified, include only the signature (name, parameters, return type), not the body. This reduces a 50-line function to 1-2 lines.

**Skeleton mode**: For files that provide structural context, include the file structure (imports, class/function names with line numbers) but not the implementation details.

**Full mode**: For files that are being actively modified, include the full content. Never compress the active working file.

Choose the mode based on how the content is being used:
- Active editing target: Full mode
- Called by the active target: Signature-only mode
- In the same module but not directly related: Skeleton mode
- In a different module: Omit entirely (load on demand via LSP)

### Step 7: Compression quality metrics (compression/quality.py)

Build metrics to evaluate compression quality:

- **Compression ratio**: Output tokens / input tokens (target: 0.3-0.5)
- **Fact preservation score**: Number of facts in output / number of facts in input (target: 1.0)
- **Stability score**: Compress the output again; if the result is identical, score is 1.0. If it changes, measure the delta.
- **Readability score**: Can the compressed output be understood without the original? (Heuristic: every sentence has a subject and a verb, every file path is complete)

Log these metrics for every compression operation so the system can be tuned over time.

### Step 8: Wire into the rest of the system

Integration points:
- Mission 20 (Context Window Management): The compactor calls the compression pipeline
- Mission 21 (Memory System): Session memory and knowledge base use fact extraction for storage
- Mission 22 (Session Handoff): Handoff documents are compressed before storage
- Mission 23 (Multi-Agent): Worker agent results are compressed before being sent to the lead

### Step 9: Write tests

- Test structural stripping preserves all facts while removing filler
- Test tool output compression on real grep output, test output, and compiler output
- Test fact extraction on 10 diverse conversation samples, verify zero fact loss
- Test semantic deduplication merges duplicates correctly
- Test code context compression modes produce correct output
- Test stability: compress output 5 times in a row, verify it stabilizes by iteration 2
- Benchmark compression ratio on a 50,000-token conversation sample

## Acceptance Criteria

- The full pipeline achieves 50-70% token reduction on typical conversations
- Zero facts are lost during compression (fact preservation score = 1.0)
- Compression is stable (re-compressing produces identical output within 2 iterations)
- Tool output compression achieves at least 40% reduction
- Code context compression correctly selects modes based on usage
- Quality metrics are logged for every compression operation
- No source file exceeds 400 lines

## Key Research References

- Erold Smart Strip: lossless fact extraction surviving unlimited re-compression
- Anthropic compact-2026 API: trigger-based automatic compaction
- LangChain Deep Agents: autonomous compression at natural breakpoints
- Zylos Research: 80-90% reduction via embedding-based compression
- Lost-in-the-middle research: models attend poorly to middle-context information

## Estimated Complexity

Very High. The fact extraction engine (Stage 3) is the hardest component. Determining what is a "fact" versus "filler" versus "reasoning" requires sophisticated NLP or LLM-assisted classification. Getting zero-fact-loss compression requires extensive testing across diverse content types. The stability requirement (no drift on re-compression) rules out most naive summarization approaches.
