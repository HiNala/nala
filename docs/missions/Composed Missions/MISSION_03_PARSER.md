# Mission 03: Tree-sitter Parser and Metrics Engine

## Objective

Parse source files into ASTs using Tree-sitter, extract symbols (functions, classes, imports, calls), and compute code quality metrics (cyclomatic complexity, SLOC, cognitive complexity). After this mission, Nala understands the internal structure of every file.

## Why This Matters

This transforms raw text files into structured, queryable data. Without this, Nala is a file browser. With this, Nala knows every function, every class hierarchy, every import relationship, and how complex each code unit is. This data feeds into the Neo4j graph (Mission 07) and analysis perspectives (Mission 09).

Tree-sitter is the industry standard — used by GitHub for syntax highlighting, NeoVim for semantic highlighting, Cursor and OpenCode for codebase intelligence. It parses incrementally (updates an existing AST in sub-millisecond time when a file changes) and supports 100+ languages.

## Status

**Core implementation in place.** See:
- `rust-core/nala-indexer/src/parser.rs` — Tree-sitter integration, language detection, symbol extraction for Rust/Python/JS/TS/Go
- `rust-core/nala-indexer/src/symbol_graph.rs` — Symbol types and SymbolKind enum
- `rust-core/nala-indexer/src/metrics.rs` — Line-based complexity metrics (Tree-sitter + rust-code-analysis integration in this mission)

## Implementation Steps for This Mission

### Step 1: Integrate rust-code-analysis (metrics.rs upgrade)

Replace the current line-count heuristics with [rust-code-analysis](https://github.com/mozilla/rust-code-analysis) for accurate per-function metrics. Add to nala-indexer/Cargo.toml:

```toml
# Note: rust-code-analysis requires tree-sitter to be compatible version
# rust-code-analysis = "0.0.25"
```

Wrap in a feature flag `#[cfg(feature = "advanced-metrics")]` so the basic implementation still compiles without it.

### Step 2: Expand language support

Add these grammars (each is a separate crate):
- tree-sitter-java
- tree-sitter-cpp
- tree-sitter-c
- tree-sitter-ruby
- tree-sitter-swift (if available)

Each needs a LanguageExtractor implementation in parser.rs. Split into separate files when parser.rs approaches 400 lines:
- `parser/rust_extractor.rs`
- `parser/python_extractor.rs`
- `parser/js_extractor.rs`
- `parser/go_extractor.rs`

### Step 3: Cache symbol data in SQLite

After parsing, store a JSON blob of extracted symbols in `file_index.symbol_data`. On subsequent launches for unchanged files, load from cache instead of re-parsing.

### Step 4: Update the PyO3 bridge

Extend `nala-bridge/src/lib.rs` with:
- `get_symbols(path, language)` — return symbols for a file as JSON
- `get_metrics(path)` — return metrics as JSON

### Step 5: Tests

Test with real code samples:
- Parse a Rust file with structs, traits, functions, use statements
- Parse a Python file with classes, decorators, async functions
- Verify cyclomatic complexity matches manual calculation

## Acceptance Criteria

- [ ] Tree-sitter correctly parses all 5 supported languages
- [ ] Symbol extraction produces correct function/class/import data
- [ ] Metrics include cyclomatic complexity per function
- [ ] 10,000-file project indexes in under 30 seconds on first run
- [ ] Subsequent index (no changes) completes in under 2 seconds
- [ ] No source file exceeds 400 lines (split language extractors if needed)
- [ ] All tests pass

## Key Dependencies

- tree-sitter, tree-sitter-{rust,python,javascript,typescript,go}
- rust-code-analysis (Mozilla) — optional feature
- rayon (parallel processing)
