# Mission 06: PyO3 Bridge and Python Scaffold

## Objective

Build the PyO3 bridge that exposes the Rust indexer's data to Python, and set up the Python orchestration layer with its core modules. After this mission, Python code can call Rust functions to get parsed symbols, metrics, and scan results, and the Python package structure is ready for the graph, perspectives, LLM, and session modules.

## Why This Matters

The Rust core is fast but not flexible. Python is flexible but not fast. The PyO3 bridge gives us both: Rust does the heavy parsing and metrics computation, then hands the structured data to Python for orchestration, graph population, AI calls, and report generation. This is the same architecture pattern used by tools like Polars, tiktoken, and Pydantic V2 where performance-critical code lives in Rust and the developer-facing API is Python. The key guidance from PyO3 best practices is to minimize the number of cross-language calls and send data in bulk rather than item by item.

## Implementation Steps

### Step 1: Define the PyO3 data types (nala-bridge/src/lib.rs)

Create Python-visible versions of the core Rust types using `#[pyclass]`:

- `PyScannedFile`: relative_path, extension, size_bytes, content_hash
- `PySymbol`: kind (string), name, file_path, start_line, end_line, metadata (dict)
- `PyMetricsResult`: file_path, function_name, cyclomatic_complexity, cognitive_complexity, sloc, ploc, cloc, halstead_volume, halstead_difficulty
- `PyScanResult`: total_files, changed_count, new_count, deleted_count, scan_duration_ms
- `PyIndexResult`: scan_result (PyScanResult), symbols (list of PySymbol), metrics (list of PyMetricsResult), index_duration_ms

Use `#[pymethods]` to implement `__repr__` and property getters for each class.

### Step 2: Expose the core functions

Create these `#[pyfunction]` entries in the module:

- `scan(path: &str) -> PyResult<PyScanResult>`: Calls the Rust scanner/hasher
- `index(path: &str) -> PyResult<PyIndexResult>`: Calls the full indexer
- `get_symbols(path: &str) -> PyResult<Vec<PySymbol>>`: Returns cached symbols for a file
- `get_metrics(path: &str) -> PyResult<Vec<PyMetricsResult>>`: Returns cached metrics for a file
- `get_all_symbols(project_path: &str) -> PyResult<Vec<PySymbol>>`: Returns all symbols across the project
- `version() -> &str`: Returns the version string

Register all functions and classes in the `#[pymodule]` definition.

### Step 3: Handle data conversion efficiently

Follow PyO3 best practice: do as much work as possible in Rust before crossing the boundary. The `index()` function should run the entire scan-parse-extract-metrics pipeline in Rust and return a single large result object, not make many small calls.

For large symbol lists, convert to Python lists in a single batch operation. Avoid per-item conversion in a Python loop.

### Step 4: Build the Python orchestration scaffold

Set up the `python-orchestrator/nala_orchestrator/` package with these modules:

**config.py**: A `NalaConfig` dataclass that holds:
- project_root (Path)
- neo4j_uri (str, default "bolt://localhost:7687")
- neo4j_user (str, default "neo4j")
- neo4j_password (str)
- llm_provider (str, default "anthropic")
- llm_model (str, default "claude-sonnet-4-20250514")
- llm_api_key (str, from env var)
- session_dir (Path, default .nala/sessions/)

Load from `.nala/config.toml` if it exists, with environment variable overrides.

**graph/__init__.py**: Stub imports for connection, schema, queries, builder.
**perspectives/__init__.py**: Stub imports for all perspective classes.
**llm/__init__.py**: Stub imports for provider abstraction.
**sessions/__init__.py**: Stub imports for session manager.
**agents/__init__.py**: Stub imports for orchestrator.

### Step 5: Build the graph connection module (graph/connection.py)

Create a `GraphConnection` class that:
- Connects to Neo4j using the neo4j Python driver
- Handles connection errors gracefully (Neo4j might not be running)
- Provides `run_query(cypher: str, params: dict) -> list` for executing Cypher queries
- Provides `close()` for clean shutdown
- Uses connection pooling for efficiency

### Step 6: Build the graph schema module (graph/schema.py)

Define the Neo4j schema as constants:

Node labels: File, Function, Class, Module, Import
Relationship types: CONTAINS (File->Function, File->Class), CALLS (Function->Function), IMPORTS (File->Module), DEPENDS_ON (Module->Module), DEFINES (File->Module)

Provide a `create_constraints()` function that sets up uniqueness constraints and indexes in Neo4j for performance.

### Step 7: Verify the bridge works end-to-end

Write a Python test that:
1. Imports nala_core
2. Calls `nala_core.scan("./some-test-project")`
3. Calls `nala_core.index("./some-test-project")`
4. Verifies symbols and metrics are returned
5. Prints a summary

Write a Python test that:
1. Creates a GraphConnection
2. Runs `create_constraints()`
3. Verifies the connection works (or skips gracefully if Neo4j is not running)

## Acceptance Criteria

- `maturin develop` builds successfully
- `import nala_core` works in Python
- `nala_core.index()` returns correct symbols and metrics
- Python orchestrator package installs with `pip install -e .`
- NalaConfig loads from file and env vars correctly
- GraphConnection handles missing Neo4j gracefully
- All tests pass
- No source file exceeds 400 lines

## Key Dependencies

Rust: pyo3, maturin
Python: neo4j, tomli (TOML parsing), pydantic (config validation)

## Estimated Complexity

Medium-High. PyO3 type conversion can be fiddly, especially for nested structures. Getting the Maturin build to work cleanly in a workspace with other crates requires careful Cargo.toml configuration.
