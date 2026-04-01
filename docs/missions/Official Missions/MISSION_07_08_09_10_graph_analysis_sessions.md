# Mission 07: Neo4j Code Graph and Symbol Population

## Objective

Build the graph population pipeline that takes all symbols extracted by the Rust indexer and loads them into Neo4j as a queryable code knowledge graph. After this mission, every function, class, module, import, and call relationship in the codebase is a node or relationship in Neo4j, and Nala can answer graph queries like "what depends on this module?" or "what calls this function?"

## Why This Matters

A graph database is the natural home for code relationships. Files depend on modules, modules contain classes, classes have methods, methods call other methods, functions import from other files. These are all relationships, and Neo4j is purpose-built for traversing relationships. This is the same insight behind CodeRabbit's codegraph feature, GitHub's CodeGraph Analyzer project, and the CodeGraphContext MCP server. The difference is that Nala builds this graph locally, keeps it private, and uses it to power every analysis perspective.

## Implementation Steps

### Step 1: Graph builder (graph/builder.py)

Create a `GraphBuilder` class that takes IndexResult data from the Rust bridge and populates Neo4j. It should:

1. Clear stale data for files that have changed (delete old nodes/relationships for those files, then re-create)
2. Create File nodes with properties: path, extension, language, sloc, complexity_sum
3. Create Function nodes: name, file_path, start_line, end_line, cyclomatic_complexity, cognitive_complexity, parameter_count, visibility
4. Create Class nodes: name, file_path, start_line, end_line, field_count, method_count
5. Create Module nodes: name, path
6. Create CONTAINS relationships: File -> Function, File -> Class
7. Create IMPORTS relationships: File -> Module (with imported_names property)
8. Create CALLS relationships: Function -> Function (with line_number property)
9. Create DEPENDS_ON relationships: Module -> Module

Use batch operations (UNWIND with parameterized Cypher) for performance. Loading 10,000 symbols should take under 10 seconds.

### Step 2: Common graph queries (graph/queries.py)

Implement these reusable Cypher queries as functions:

- `get_file_dependencies(file_path) -> list[dict]`: What does this file depend on?
- `get_dependents(module_name) -> list[dict]`: What depends on this module?
- `get_function_callers(function_name) -> list[dict]`: What calls this function?
- `get_function_callees(function_name) -> list[dict]`: What does this function call?
- `get_most_connected_modules(limit) -> list[dict]`: Which modules have the most connections?
- `get_isolated_functions() -> list[dict]`: Functions with zero incoming calls
- `get_circular_dependencies() -> list[dict]`: Cycles in the dependency graph
- `get_complexity_hotspots(threshold) -> list[dict]`: Functions above a complexity threshold

### Step 3: Wire into the TUI

Add a `/graph` slash command that prints a text summary of graph stats: node counts by type, relationship counts by type, top 5 most connected modules.

### Step 4: Handle Neo4j absence gracefully

If Neo4j is not running, Nala should still work. All graph-dependent features show a message like "Neo4j is not connected. Run `neo4j start` to enable graph features." The tool never crashes because of a missing database.

## Acceptance Criteria

- All symbols from the indexer are loaded into Neo4j as nodes and relationships
- Graph queries return correct results
- Batch loading 10,000+ symbols completes in under 10 seconds
- Missing Neo4j is handled gracefully
- No source file exceeds 400 lines

---

# Mission 08: Pre-Analysis Chunking and Interactive Selection

## Objective

Build the pre-analysis system that breaks a codebase into logical chunks (by module, by directory, by feature area) and presents them to the user interactively so they can choose what to analyze. This makes the experience feel guided and fun rather than an opaque batch job.

## Why This Matters

On a large codebase, running every analysis perspective on every file takes time and produces overwhelming output. By letting the user pick sections, they stay in control and get focused results. This is a key differentiator from tools that just dump a wall of output.

## Implementation Steps

### Step 1: Chunking strategies (Python: perspectives/chunking.py)

Implement three chunking strategies:

**By Directory**: Group files by their top-level directory. Each directory becomes a chunk with a name, file count, and total SLOC.

**By Module**: Group files by their detected module (using import analysis from the graph). Files that import each other heavily are in the same chunk.

**By Complexity Tier**: Group files into tiers: Low (avg complexity < 5), Medium (5-15), High (> 15). This lets users focus on the most problematic areas first.

Each strategy returns a `Vec<Chunk>` where Chunk has: name, description, file_paths (list), file_count, total_sloc, avg_complexity.

### Step 2: Interactive selection in the TUI

When the user types `/analyze`, instead of immediately running, present the chunks:

```
Pre-scan complete. Your codebase has 1,247 files in 12 sections:

  [1] src/api/        - 89 files, 4,200 SLOC, avg complexity 8.2
  [2] src/auth/       - 34 files, 1,800 SLOC, avg complexity 12.1 ⚠️
  [3] src/models/     - 67 files, 3,100 SLOC, avg complexity 5.4
  ...

  [A] Analyze ALL sections
  [H] Analyze HIGH complexity sections only

Select sections (comma-separated, or A/H):
```

The user picks sections and the analysis runs only on those files.

### Step 3: Cache chunk definitions

Store the chunk breakdown in the session so subsequent analyses can reuse the same chunking without re-computing. Update chunks only when the file set changes significantly.

## Acceptance Criteria

- At least three chunking strategies work correctly
- Interactive selection in the TUI works with keyboard input
- Only selected chunks are passed to the analysis engine
- Chunk data is cached for reuse

---

# Mission 09: Analysis Perspectives Engine

## Objective

Build the perspective engine that applies analytical lenses to the codebase (or selected chunks). Each perspective produces structured findings with severity levels and actionable recommendations. This is the analytical brain of Nala.

## Why This Matters

This is what makes Nala more than a code browser. The perspectives transform raw data (metrics, graph relationships, git history) into actionable insights. Each perspective answers a specific question: "Where is the complexity?", "What are the dependency risks?", "What code is untested?", "What changes the most?", "What is dead?"

## Implementation Steps

### Step 1: Base perspective class (perspectives/base.py)

Create an abstract `Perspective` base class:
- `name: str` (e.g., "complexity", "dependency")
- `description: str`
- `analyze(files: list, graph: GraphConnection, config: NalaConfig) -> PerspectiveResult`
- `PerspectiveResult` contains: perspective_name, findings (list of Finding), summary (str), stats (dict)
- `Finding` contains: severity (Critical/High/Medium/Low/Info), file_path, line_start, line_end, message, recommendation, related_symbols (list)

### Step 2: Complexity perspective (perspectives/complexity.py)

Queries metrics data from the Rust bridge. Flags functions where cyclomatic_complexity > 10 (configurable threshold) or cognitive_complexity > 15. Ranks findings by severity. Generates recommendations like "Consider extracting the nested conditional logic in `process_payment()` into smaller helper functions."

### Step 3: Dependency perspective (perspectives/dependency.py)

Uses Neo4j graph queries to identify: circular dependencies, modules with fan-out > 10 (depends on too many things), modules with fan-in > 20 (too many things depend on it, high-risk change target), orphaned modules (nothing depends on them and they depend on nothing).

### Step 4: Dead code perspective (perspectives/dead_code.py)

Uses the graph to find functions and classes with zero incoming CALLS or IMPORTS relationships. Excludes entry points (main functions, test functions, exported API endpoints). Reports dead code as Low severity findings with "Consider removing this unused code" recommendations.

### Step 5: Code churn perspective (perspectives/churn.py)

Analyzes git history using `git log --numstat` to identify files that change frequently. Cross-references high-churn files with high-complexity files to find "risk hotspots" (frequently changing AND complex). These are the areas most likely to introduce bugs.

### Step 6: Test coverage perspective (perspectives/coverage.py)

Reads coverage reports (lcov, coverage.py JSON, Jest JSON) if they exist. Maps coverage percentages onto the code graph. Identifies untested functions and classes, especially those with high complexity (untested AND complex = highest risk).

### Step 7: Performance perspective (perspectives/performance.py)

Pattern-based analysis that flags known anti-patterns: nested loops (O(n^2) risk), synchronous I/O in async functions, unbounded list growth, missing pagination, N+1 query patterns (if ORM code is detected). This uses AST pattern matching via the Rust bridge rather than runtime profiling.

### Step 8: Perspective runner

Create a `run_perspectives(selected: list[str], chunks: list[Chunk], ...) -> AnalysisResult` function that runs the selected perspectives, collects all findings, deduplicates, sorts by severity, and returns a unified AnalysisResult.

## Acceptance Criteria

- Each perspective produces correct, actionable findings
- Severity levels are assigned appropriately
- Perspectives run independently and can be combined
- Running all perspectives on a 50,000-line codebase completes in under 60 seconds
- No source file exceeds 400 lines

---

# Mission 10: Session Management and Report Generation

## Objective

Build the session system that saves every analysis run as a structured session with markdown reports, and the report generator that produces comprehensive, human-readable audit documents from analysis results.

## Why This Matters

Without sessions, analysis results disappear when you close the terminal. Sessions give Nala a memory. They let you track progress over time, compare the health of your codebase between versions, and hand reports to teammates or stakeholders. The markdown reports are the primary deliverable that makes Nala useful beyond just viewing results in the TUI.

## Implementation Steps

### Step 1: Session manager (sessions/manager.py)

Create a `SessionManager` that:
- Creates `.nala/sessions/` directory if it does not exist
- For each analysis run, creates a timestamped subdirectory: `.nala/sessions/2026-03-31_14-30-00/`
- Saves session metadata as `session.json`: timestamp, project_root, perspectives_run, chunk_selection, total_findings, finding_counts_by_severity
- Saves the full AnalysisResult as `results.json`
- Provides `list_sessions() -> list[SessionSummary]` to enumerate past sessions
- Provides `load_session(session_id: str) -> SessionData` to reload a session
- Provides `compare_sessions(a: str, b: str) -> SessionDiff` to compare two sessions (new findings, resolved findings, changed severity)

### Step 2: Report generator (sessions/report.py)

Create a `ReportGenerator` that takes an AnalysisResult and produces a comprehensive markdown report:

The report structure:
- Header: project name, date, perspectives run, scope (which chunks)
- Executive summary: total findings, breakdown by severity, top 3 risk areas
- Per-perspective sections: each perspective gets its own section with findings grouped by file, ordered by severity
- Each finding includes: severity badge, file path with line numbers, description, recommendation, related code (short snippet if available)
- Appendix: full metrics summary table (top 20 most complex functions), dependency graph summary

Save the report as `report.md` in the session directory.

### Step 3: Wire into the TUI

After an analysis completes:
1. Save the session automatically
2. Display the executive summary in the main area
3. Show a message: "Full report saved to .nala/sessions/2026-03-31_14-30-00/report.md"
4. The `/sessions` command lists past sessions
5. The `/session <id>` command loads and displays a past session's summary

## Acceptance Criteria

- Sessions are saved automatically after every analysis
- Reports are well-formatted markdown that renders cleanly in any markdown viewer
- Session comparison correctly identifies new and resolved findings
- Past sessions can be loaded and displayed in the TUI
- No source file exceeds 400 lines
