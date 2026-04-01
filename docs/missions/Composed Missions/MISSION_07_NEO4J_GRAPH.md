# Mission 07: Neo4j Code Knowledge Graph

## Objective

Populate a Neo4j graph database with the symbols extracted by the indexer and make it queryable from Python. After this mission, Nala can answer relationship-based questions like "what functions call X?", "which files import module Y?", and "show me the dependency chain from A to B" — queries that would require recursive CTEs in SQL but are three lines of Cypher.

## Why This Matters

A flat list of symbols is searchable but not traversable. Knowing that `authenticate()` calls `hash_password()` calls `bcrypt.hash()` is structurally different from knowing all three functions exist. Graph traversal unlocks call-chain analysis, dead code detection, circular dependency finding, and impact analysis — all of which are table-stakes features for a serious code intelligence tool. Neo4j's APOC library and native Cypher make this trivial; the equivalent SQL is fragile and slow.

Neo4j is **optional**. Every feature that requires it degrades gracefully when the database is unavailable.

## Context

The Python orchestration layer already has a `graph/` stub from Mission 01. The indexer (Rust) has already extracted symbols. The bridge between them is JSON serialisation: the indexer produces a list of symbols as JSON, the Python graph builder reads them and creates nodes/relationships in Neo4j.

## Implementation Steps

### Step 1: Schema design

Define the node labels and relationship types:

**Nodes:**
- `File` — `{path: str, language: str, sloc: int, complexity: float}`
- `Function` — `{name: str, file_path: str, start_line: int, end_line: int, complexity: int, param_count: int, is_public: bool}`
- `Class` — `{name: str, file_path: str, start_line: int, method_count: int}`
- `Module` — `{name: str}` (logical grouping, not necessarily a file)
- `Import` — `{name: str, source: str, is_wildcard: bool}`

**Relationships:**
- `(File)-[:CONTAINS]->(Function)`
- `(File)-[:CONTAINS]->(Class)`
- `(Function)-[:CALLS]->(Function)` (where call target is resolved)
- `(Function)-[:DEFINED_IN]->(Class)` (for methods)
- `(File)-[:IMPORTS]->(File)` (resolved imports)
- `(File)-[:IMPORTS_MODULE]->(Module)` (unresolved/external imports)

### Step 2: Build GraphConnection (graph/connection.py)

Create `nala_orchestrator/graph/connection.py`:

```python
from neo4j import GraphDatabase, Driver
from typing import Optional
import logging

log = logging.getLogger(__name__)

class GraphConnection:
    def __init__(self, uri: str, user: str, password: str):
        self._driver: Optional[Driver] = None
        self._uri = uri
        self._user = user
        self._password = password

    def connect(self) -> bool:
        """Attempt to connect. Returns True on success."""
        try:
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            log.warning("Neo4j unavailable: %s", e)
            return False

    def is_available(self) -> bool:
        return self._driver is not None

    def run(self, cypher: str, **params) -> list[dict]:
        if not self._driver:
            return []
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return [dict(r) for r in result]

    def close(self):
        if self._driver:
            self._driver.close()
```

### Step 3: Build GraphBuilder (graph/builder.py)

Create `nala_orchestrator/graph/builder.py`. This class accepts a list of symbols (dicts matching the schema from nala-indexer) and upserts them into Neo4j.

Key methods:
- `build_from_symbols(symbols: list[dict]) -> BuildResult` — main entry point
- `_upsert_file(tx, file_path, language)` — MERGE on path
- `_upsert_function(tx, sym)` — MERGE on (name, file_path)
- `_upsert_class(tx, sym)` — MERGE on (name, file_path)
- `_create_contains(tx, file_path, sym_name, sym_type)` — MERGE relationship
- `_create_calls(tx, caller, callee)` — MERGE CALLS relationship

Use MERGE (not CREATE) everywhere so re-indexing is idempotent.

Run all upserts inside a transaction for atomicity. Use `UNWIND` with parameter arrays for bulk inserts (much faster than one query per symbol).

### Step 4: Query helpers (graph/queries.py)

Create `nala_orchestrator/graph/queries.py` with pre-built Cypher queries:

```python
# Find all functions with complexity above a threshold
COMPLEX_FUNCTIONS = """
MATCH (f:Function)
WHERE f.complexity > $threshold
RETURN f.name, f.file_path, f.complexity
ORDER BY f.complexity DESC
LIMIT $limit
"""

# Find the call chain from one function to another (BFS, depth-limited)
CALL_CHAIN = """
MATCH path = shortestPath(
    (a:Function {name: $from})-[:CALLS*1..10]->(b:Function {name: $to})
)
RETURN path
"""

# Dead code: functions defined but never called
DEAD_FUNCTIONS = """
MATCH (f:Function)
WHERE NOT (f)<-[:CALLS]-()
  AND f.is_public = false
RETURN f.name, f.file_path
"""

# Circular dependencies between files
CIRCULAR_DEPS = """
MATCH path = (a:File)-[:IMPORTS*2..6]->(a)
RETURN path LIMIT 20
"""

# Files that import the most modules (high coupling)
HIGH_COUPLING = """
MATCH (f:File)-[:IMPORTS_MODULE]->(m:Module)
WITH f, count(m) as import_count
WHERE import_count > $threshold
RETURN f.path, import_count
ORDER BY import_count DESC
"""
```

### Step 5: Integration with AgentOrchestrator

In `agents/orchestrator.py`, add a `graph: Optional[GraphConnection]` field. When Neo4j is available, include graph query results in the system prompt context:

```python
def _build_context(self) -> str:
    ctx = [f"Project: {self.project_root}"]
    ctx.append(f"Files: {self.context.total_files}, Symbols: {self.context.total_symbols}")
    if self.graph and self.graph.is_available():
        # Inject top-5 most complex functions as context
        complex = self.graph.run(COMPLEX_FUNCTIONS, threshold=10, limit=5)
        if complex:
            ctx.append("High-complexity functions: " + ", ".join(
                f"{r['f.name']} (CC={r['f.complexity']})" for r in complex
            ))
    return "\n".join(ctx)
```

### Step 6: CLI command and tests

Add a `/graph` slash command to the TUI (`handle_slash_command` in `app.rs`) that sends a `graph_status` request over IPC and displays whether Neo4j is connected, how many nodes exist, and whether any circular dependencies were found.

Write Python tests:
- `test_graph_builder.py` — mock Neo4j driver, verify MERGE queries are called correctly
- `test_queries.py` — verify Cypher strings are valid (use `neo4j` driver's `.query_summary()` in a test Neo4j instance if available, otherwise just syntax-check)

## Acceptance Criteria

- `GraphConnection.connect()` returns False gracefully when Neo4j is not running
- `GraphBuilder.build_from_symbols()` creates correct node types and relationships
- All Cypher queries execute without error on a test dataset
- Re-running the builder on the same symbols produces no duplicates (MERGE is idempotent)
- `AgentOrchestrator` works correctly when Neo4j is unavailable (graceful degradation)
- No file exceeds 400 lines

## Key Dependencies

- neo4j (Python driver, v5+)
- pytest-mock (for unit tests)
- A running Neo4j 5.x instance for integration tests (skip if not available)

## Estimated Complexity

Medium-high. The graph schema design and MERGE-based idempotent writes require care. The rest is straightforward plumbing.
