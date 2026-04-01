# Mission 01: Project Setup and Scaffolding

## Objective

Set up the complete project structure, initialize the Rust workspace with all crates, initialize the Python package, configure CI, and ensure everything compiles and passes a basic smoke test. This mission produces the skeleton that every subsequent mission builds on.

## Why This Matters

A well-structured project from day one prevents the kind of structural debt that slows teams down later. The Rust workspace needs to be split into small, focused crates so that compilation is fast (only changed crates recompile) and responsibilities are clear. The Python package needs proper packaging with pyproject.toml so it installs cleanly. Getting this right now means every future mission starts from a solid foundation.

## Context

Nala is a hybrid Rust/Python application. The Rust side is a Cargo workspace containing multiple crates (nala-cli, nala-tui, nala-indexer, nala-lsp, nala-bridge). The Python side is a single package (nala_orchestrator) that imports the Rust bridge via PyO3/Maturin. Both sides need to be set up so that `cargo build` compiles the Rust workspace and `maturin develop` builds the PyO3 bridge and installs it into a Python virtualenv.

## Implementation Steps

### Step 1: Create the root project directory

Create the `nala/` root directory with a top-level README.md, LICENSE (MIT), and .gitignore. The .gitignore should cover Rust targets, Python venvs, __pycache__, .nala session directories, Neo4j data, and common editor files.

### Step 2: Initialize the Rust workspace

Create `rust-core/Cargo.toml` as a workspace manifest with five member crates:

- `nala-cli` (binary crate, the entry point)
- `nala-tui` (library crate, terminal user interface)
- `nala-indexer` (library crate, file scanning, parsing, and metrics)
- `nala-lsp` (library crate, LSP client)
- `nala-bridge` (library crate with cdylib output, PyO3 bindings)

Each crate gets its own Cargo.toml and src/ directory. Use `cargo init` or manual creation. Set the Rust edition to 2021. Set the MSRV to 1.75.0 or later (needed for async traits and modern features).

### Step 3: Add initial dependencies to each crate

nala-cli: clap (CLI argument parsing), tokio (async runtime), nala-tui (workspace dependency), nala-indexer (workspace dependency)

nala-tui: ratatui, crossterm (terminal backend), tokio

nala-indexer: tree-sitter, tree-sitter-rust (start with Rust grammar, add more later), rusqlite (SQLite), sha2 (content hashing), walkdir (directory traversal), serde + serde_json (serialization)

nala-lsp: tower-lsp (or lsp-types for client-side), tokio

nala-bridge: pyo3 (with extension-module feature), nala-indexer (workspace dependency)

### Step 4: Write minimal code for each crate

nala-cli/src/main.rs: Parse CLI args with clap. Accept a `--path` argument (defaults to current directory). Print "Nala v0.1.0" and exit. This proves the binary compiles and runs.

nala-tui/src/lib.rs: Export a placeholder `run_tui()` function that returns Ok(()).

nala-indexer/src/lib.rs: Export placeholder modules (scanner, hasher, parser, metrics, symbol_graph, cache). Each module has a single placeholder function.

nala-lsp/src/lib.rs: Export a placeholder `LspManager` struct.

nala-bridge/src/lib.rs: Use the `#[pymodule]` macro to create a `nala_core` Python module with a single `version()` function that returns "0.1.0".

### Step 5: Initialize the Python package

Create `python-orchestrator/` with:
- pyproject.toml (using hatchling or setuptools, with nala_core as a dependency via maturin)
- nala_orchestrator/__init__.py
- nala_orchestrator/config.py (placeholder Config class)
- Subdirectory stubs for graph/, perspectives/, llm/, sessions/, agents/ (each with __init__.py)

### Step 6: Set up the Maturin build

In the nala-bridge crate, configure Cargo.toml for PyO3 + Maturin:
```toml
[lib]
name = "nala_core"
crate-type = ["cdylib", "rlib"]
```

Create a pyproject.toml in the nala-bridge directory for Maturin builds. Verify that `maturin develop` inside a Python venv produces an importable `nala_core` module.

### Step 7: Create the dashboard stub

Create `dashboard/` with a requirements.txt (fastapi, uvicorn, neo4j) and a placeholder server.py that starts a FastAPI app on localhost:3000 with a single health-check endpoint.

### Step 8: Set up CI

Create `.github/workflows/ci.yml` with:
- Rust: cargo fmt --check, cargo clippy, cargo test
- Python: ruff lint, pytest (once tests exist)
- Matrix: ubuntu-latest, macos-latest

### Step 9: First commit

Initialize git, create an initial commit with all scaffolding, verify everything compiles with `cargo build --workspace`, and verify the Python bridge with `maturin develop && python -c "import nala_core; print(nala_core.version())"`.

## Acceptance Criteria

- `cargo build --workspace` succeeds with zero errors
- `cargo clippy --workspace` reports zero warnings
- `cargo test --workspace` runs (even if no tests yet, it should not fail)
- `maturin develop` builds the PyO3 bridge
- `python -c "import nala_core; print(nala_core.version())"` prints "0.1.0"
- Project structure matches the layout defined in the Master Plan
- No source file exceeds 100 lines (at this stage, everything is stubs)
- .gitignore covers all generated artifacts
- README.md exists with a brief project description

## Files Created

~25-30 files across the Rust workspace, Python package, dashboard stub, and CI config.

## Estimated Complexity

Medium. Mostly boilerplate and configuration, but getting the PyO3/Maturin bridge working correctly on first try requires careful attention to Cargo.toml configuration.
