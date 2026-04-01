# Mission 03: Tree-sitter Parser and Metrics Engine

## Objective

Build the code parsing engine that takes scanned files, parses them into abstract syntax trees using Tree-sitter, extracts symbols (functions, classes, modules, imports, calls), and computes code quality metrics (cyclomatic complexity, cognitive complexity, lines of code, Halstead metrics). After this mission, Nala understands the internal structure of every source file.

## Why This Matters

This is the intelligence layer that transforms raw text files into structured, queryable data. Without this, Nala is just a file browser. With this, Nala knows every function name, every class hierarchy, every import relationship, and how complex each piece of code is. This data feeds directly into the Neo4j code graph (Mission 07) and the analysis perspectives (Mission 09).

Tree-sitter is the industry standard for this. It is used by GitHub for syntax highlighting and code navigation, by NeoVim for semantic highlighting, and by tools like Cursor and OpenCode for codebase understanding. It parses incrementally, meaning when a file changes, it updates the existing syntax tree in sub-millisecond time rather than re-parsing from scratch.

## Context

This work happens in the `nala-indexer` crate, building on the scanner and hasher from Mission 02. The parser processes only changed files (as identified by the content hash comparison), making indexing fast after the initial scan.

## Implementation Steps

### Step 1: Set up Tree-sitter grammars (parser.rs)

Create a `Parser` struct that manages Tree-sitter parser instances for multiple languages. Start with support for these languages (each requires its own Tree-sitter grammar crate):

- Rust (tree-sitter-rust)
- Python (tree-sitter-python)
- JavaScript (tree-sitter-javascript)
- TypeScript (tree-sitter-typescript)
- Go (tree-sitter-go)

Add more languages incrementally in later missions. The parser should detect language from file extension and select the appropriate grammar.

Create a `detect_language(extension: &str) -> Option<Language>` function that maps file extensions to Tree-sitter Language objects.

### Step 2: Parse files into syntax trees (parser.rs continued)

Create a `parse_file(path: &Path, language: Language) -> Result<ParsedFile>` function that:
1. Reads the file content
2. Creates a Tree-sitter parser for the language
3. Parses the content into a Tree-sitter Tree
4. Returns a `ParsedFile` struct containing: path, language, tree (the AST), source_code (the raw text), parse_errors (Vec of any error nodes found)

Handle parse errors gracefully. Tree-sitter is error-tolerant and will produce a partial tree even for files with syntax errors. Log errors but do not fail.

### Step 3: Extract symbols from syntax trees (symbol_graph.rs)

Create a `SymbolExtractor` that walks a Tree-sitter syntax tree and extracts these symbol types:

- Functions: name, start_line, end_line, parameter_count, return_type (if available), visibility (public/private)
- Classes/Structs: name, start_line, end_line, field_count, method_names
- Modules/Namespaces: name, path
- Imports: source module, imported names, whether it is a wildcard import
- Function Calls: caller function, called function name, line number

Each extracted symbol becomes a `Symbol` struct with: kind (enum: Function, Class, Module, Import, Call), name, file_path, start_line, end_line, metadata (HashMap for language-specific extras).

The extraction logic is language-specific. Create a trait `LanguageExtractor` with methods for each symbol type, and implement it for each supported language. Start with Rust and Python extractors. The key is to walk the AST using Tree-sitter's cursor API, matching node types specific to each language.

For Rust, function nodes are `function_item`, structs are `struct_item`, imports are `use_declaration`.
For Python, functions are `function_definition`, classes are `class_definition`, imports are `import_statement` and `import_from_statement`.

### Step 4: Compute code metrics (metrics.rs)

Integrate `rust-code-analysis` (the Mozilla crate) to compute metrics per function and per file:

- Cyclomatic Complexity (CC): Number of linearly independent paths through the code. Higher means more complex branching logic.
- Cognitive Complexity: Measures how hard code is to understand, penalizing deeply nested structures.
- SLOC: Source lines of code (non-blank, non-comment)
- PLOC: Physical lines of code (all lines)
- CLOC: Comment lines of code
- BLANK: Blank lines
- Halstead Metrics: Volume, Difficulty, Effort, estimated Bugs, estimated Time to understand

Create a `MetricsResult` struct that holds all metrics for a single function or file. Create a `compute_metrics(source: &str, language: &str) -> Result<Vec<MetricsResult>>` function.

If rust-code-analysis does not support a given language, fall back to basic line counting (SLOC/PLOC/CLOC/BLANK) using a simple line-by-line analysis.

### Step 5: Build the IndexResult (lib.rs additions)

Create an `index_project(root: &Path) -> Result<IndexResult>` function that:
1. Runs `scan_project()` from Mission 02 to get changed files
2. For each changed file, detects language, parses with Tree-sitter, extracts symbols, computes metrics
3. Returns an `IndexResult` containing: scan_result (from Mission 02), parsed_files (Vec<ParsedFile>), symbols (Vec<Symbol>), metrics (Vec<MetricsResult>), index_duration (Duration)

Process files in parallel using Rayon. Each file is independent, so this parallelizes well.

### Step 6: Update the SQLite cache with symbol data

After indexing, update the cache entries with: language, symbol_count, and a JSON blob of extracted symbols. This means subsequent launches can load symbol data from the cache without re-parsing unchanged files.

### Step 7: Write tests

- Parse a known Rust file and verify that functions, structs, and imports are correctly extracted
- Parse a known Python file and verify the same
- Compute metrics on a known function and verify cyclomatic complexity matches manual calculation
- Test incremental indexing: parse all files, modify one, re-index, and verify only the modified file is re-parsed

### Step 8: Add a CLI command

Add an `index` subcommand to nala-cli that runs `index_project()` and prints a summary: total symbols found, breakdown by type (functions, classes, modules, imports), top 10 most complex functions.

## Acceptance Criteria

- Tree-sitter correctly parses Rust and Python files without crashes
- Symbol extraction produces correct function, class, and import data
- Metrics computation produces correct cyclomatic complexity values
- Incremental indexing only re-parses changed files
- A 10,000-file project indexes in under 30 seconds on first run
- Subsequent indexing (no changes) completes in under 2 seconds
- All tests pass
- No source file exceeds 400 lines (split language extractors into separate files)

## Key Dependencies

- tree-sitter (core parser)
- tree-sitter-rust, tree-sitter-python, tree-sitter-javascript, tree-sitter-typescript, tree-sitter-go (grammars)
- rust-code-analysis (metrics, depends on tree-sitter internally)
- rayon (parallel processing)

## Estimated Complexity

High. Tree-sitter's API requires careful handling of cursors and node types. Language-specific symbol extraction is the most labor-intensive part because each language has different AST structures.
