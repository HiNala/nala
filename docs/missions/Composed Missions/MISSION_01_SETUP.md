# Mission 01: Project Setup and Scaffolding

## Objective

Initialize the complete project structure: Rust workspace with all five crates, Python orchestrator package, CI configuration, and verify everything compiles and the PyO3 bridge is importable. This mission produces the skeleton every subsequent mission builds upon.

## Why This Matters

A well-structured project from day one prevents structural debt. The Rust workspace uses multiple small crates so compilation is fast (only changed crates recompile) and responsibilities are clear. Getting the PyO3/Maturin bridge working correctly from the start means Python can call Rust code from Mission 02 onward without retrofitting. Every subsequent mission assumes this foundation is solid.

## Context

Nala is a hybrid Rust/Python application:
- **Rust side:** Cargo workspace with five crates (nala-cli, nala-tui, nala-indexer, nala-lsp, nala-bridge)
- **Python side:** `nala_orchestrator` package that imports the Rust bridge via PyO3/Maturin as `nala_core`
- **Build tool:** Maturin handles building the PyO3 extension and installing it into the Python venv

The goal after this mission: `cargo build --workspace` succeeds, `maturin develop` succeeds, and `python -c "import nala_core; print(nala_core.version())"` prints "0.1.0".

---

## Step-by-Step Implementation

### Step 1: Root project files

Create these at the project root (`nala/`):

**`.gitignore`**
```
# Rust
/rust-core/target/
**/*.rs.bk

# Python
__pycache__/
*.py[cod]
*.pyo
.venv/
venv/
*.egg-info/
dist/
.eggs/

# Nala session data
.nala/

# Neo4j
neo4j_data/

# IDE / OS
.idea/
.vscode/
*.swp
*.swo
.DS_Store
Thumbs.db

# Maturin build artifacts
/python-orchestrator/nala_core*.so
/python-orchestrator/nala_core*.pyd
/rust-core/nala-bridge/target/
```

**`README.md`** — Keep brief at this stage. Just: project name, one-line description, "See docs/missions/MISSION_00_MASTER_PLAN.md for the full vision."

**`LICENSE`** — MIT license with current year.

### Step 2: Rust workspace manifest

Create `rust-core/Cargo.toml`:

```toml
[workspace]
members = [
    "nala-cli",
    "nala-tui",
    "nala-indexer",
    "nala-lsp",
    "nala-bridge",
]
resolver = "2"

[workspace.package]
version = "0.1.0"
edition = "2021"
rust-version = "1.75"
authors = ["Nala Contributors"]
license = "MIT"

[workspace.dependencies]
# Async runtime
tokio = { version = "1", features = ["full"] }

# TUI
ratatui = "0.29"
crossterm = "0.28"

# CLI
clap = { version = "4", features = ["derive"] }

# Serialization
serde = { version = "1", features = ["derive"] }
serde_json = "1"

# File system
walkdir = "2"

# Hashing
sha2 = "0.10"

# Parallel processing
rayon = "1"

# Database
rusqlite = { version = "0.32", features = ["bundled"] }

# Error handling
anyhow = "1"
thiserror = "2"

# Logging
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

# Python bridge
pyo3 = { version = "0.22", features = ["extension-module"] }
```

### Step 3: nala-cli crate

`rust-core/nala-cli/Cargo.toml`:
```toml
[package]
name = "nala-cli"
version.workspace = true
edition.workspace = true

[[bin]]
name = "nala"
path = "src/main.rs"

[dependencies]
nala-tui = { path = "../nala-tui" }
nala-indexer = { path = "../nala-indexer" }
tokio.workspace = true
clap.workspace = true
anyhow.workspace = true
tracing.workspace = true
tracing-subscriber.workspace = true
```

`rust-core/nala-cli/src/main.rs` — stub that prints version and exits. See scaffold code in the implementation notes below.

### Step 4: nala-tui crate

`rust-core/nala-tui/Cargo.toml`:
```toml
[package]
name = "nala-tui"
version.workspace = true
edition.workspace = true

[dependencies]
ratatui.workspace = true
crossterm.workspace = true
tokio.workspace = true
anyhow.workspace = true
tracing.workspace = true
serde.workspace = true
serde_json.workspace = true
```

### Step 5: nala-indexer crate

`rust-core/nala-indexer/Cargo.toml`:
```toml
[package]
name = "nala-indexer"
version.workspace = true
edition.workspace = true

[dependencies]
tree-sitter = "0.23"
tree-sitter-rust = "0.23"
tree-sitter-python = "0.23"
tree-sitter-javascript = "0.23"
tree-sitter-typescript = "0.23"
tree-sitter-go = "0.23"
walkdir.workspace = true
sha2.workspace = true
rayon.workspace = true
rusqlite.workspace = true
serde.workspace = true
serde_json.workspace = true
anyhow.workspace = true
thiserror.workspace = true
tracing.workspace = true

[dev-dependencies]
tempfile = "3"
```

### Step 6: nala-lsp crate

`rust-core/nala-lsp/Cargo.toml`:
```toml
[package]
name = "nala-lsp"
version.workspace = true
edition.workspace = true

[dependencies]
lsp-types = "0.97"
tokio.workspace = true
anyhow.workspace = true
tracing.workspace = true
serde.workspace = true
serde_json.workspace = true
```

### Step 7: nala-bridge crate (PyO3)

`rust-core/nala-bridge/Cargo.toml`:
```toml
[package]
name = "nala-bridge"
version.workspace = true
edition.workspace = true

[lib]
name = "nala_core"
crate-type = ["cdylib", "rlib"]

[dependencies]
nala-indexer = { path = "../nala-indexer" }
pyo3.workspace = true
anyhow.workspace = true
```

`rust-core/nala-bridge/pyproject.toml` (for Maturin):
```toml
[build-system]
requires = ["maturin>=1.7,<2.0"]
build-backend = "maturin"

[project]
name = "nala-core"
requires-python = ">=3.11"

[tool.maturin]
python-source = "."
module-name = "nala_core"
manifest-path = "Cargo.toml"
```

`rust-core/nala-bridge/src/lib.rs` — expose a `version()` function via `#[pymodule]`.

### Step 8: Python orchestrator package

`python-orchestrator/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "nala-orchestrator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "openai>=1.55.0",
    "google-generativeai>=0.8.0",
    "neo4j>=5.25.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "rich>=13.9.0",
    "pydantic>=2.10.0",
    "python-dotenv>=1.0.0",
    "click>=8.1.0",
    "httpx>=0.28.0",
]

[project.scripts]
nala-orchestrator = "nala_orchestrator.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["nala_orchestrator"]
```

Create all `__init__.py` files for each subpackage. Each just has a docstring at this stage.

### Step 9: Dashboard stub

`dashboard/requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
neo4j>=5.25.0
```

`dashboard/server.py` — Stub FastAPI app with a `/health` endpoint that returns `{"status": "ok", "app": "nala-dashboard"}`.

### Step 10: CI configuration

`.github/workflows/ci.yml`:
```yaml
name: CI

on: [push, pull_request]

jobs:
  rust:
    name: Rust ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: rust-core
      - name: Check formatting
        run: cargo fmt --manifest-path rust-core/Cargo.toml --all -- --check
      - name: Clippy
        run: cargo clippy --manifest-path rust-core/Cargo.toml --workspace -- -D warnings
      - name: Test
        run: cargo test --manifest-path rust-core/Cargo.toml --workspace

  python:
    name: Python
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install ruff
        run: pip install ruff
      - name: Lint
        run: ruff check python-orchestrator/
```

### Step 11: Stub source files

Each crate needs minimal stub code that compiles:

**nala-cli/src/main.rs:**
```rust
mod constants;
use constants::APP_NAME;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = APP_NAME, about = "Terminal-first AI coding environment")]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
    #[arg(short, long, default_value = ".")]
    path: String,
}

#[derive(Subcommand)]
enum Commands {
    /// Scan project files and compute content hashes
    Scan,
    /// Index the project (parse and extract symbols)
    Index,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    tracing_subscriber::fmt::init();

    match cli.command {
        Some(Commands::Scan) => println!("scan not yet implemented"),
        Some(Commands::Index) => println!("index not yet implemented"),
        None => println!("{} v{}", APP_NAME, env!("CARGO_PKG_VERSION")),
    }
    Ok(())
}
```

**nala-cli/src/constants.rs:**
```rust
/// The application name. Change here to rename the entire app.
pub const APP_NAME: &str = "nala";
pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
```

**nala-bridge/src/lib.rs:**
```rust
use pyo3::prelude::*;

/// Returns the current version of the nala_core native module.
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// The nala_core Python module.
/// Built with PyO3 + Maturin. Provides Rust-speed operations to the Python orchestrator.
#[pymodule]
fn nala_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    Ok(())
}
```

All other `lib.rs` files can be empty stubs with a single module-level doc comment.

### Step 12: Local development setup script

Create `scripts/setup.sh` (and `scripts/setup.ps1` for Windows):

```bash
#!/usr/bin/env bash
set -e
echo "Setting up Nala development environment..."

# Check Rust
command -v cargo >/dev/null || (echo "Install Rust: https://rustup.rs" && exit 1)

# Check Python 3.11+
command -v python3 >/dev/null || (echo "Install Python 3.11+" && exit 1)

# Build Rust workspace
echo "Building Rust workspace..."
cd rust-core && cargo build --workspace && cd ..

# Create Python venv
echo "Creating Python virtualenv..."
python3 -m venv .venv
source .venv/bin/activate

# Install Maturin and build bridge
echo "Building PyO3 bridge..."
pip install maturin
cd rust-core/nala-bridge && maturin develop && cd ../..

# Install Python orchestrator
echo "Installing Python orchestrator..."
cd python-orchestrator && pip install -e . && cd ..

echo ""
echo "✓ Setup complete!"
echo "  Run: source .venv/bin/activate && nala"
```

---

## Acceptance Criteria

- [ ] `cargo build --workspace` succeeds with zero errors from `rust-core/`
- [ ] `cargo clippy --workspace -- -D warnings` passes
- [ ] `cargo test --workspace` runs without failures
- [ ] `maturin develop` (from inside `rust-core/nala-bridge/` with venv active) builds the bridge
- [ ] `python -c "import nala_core; print(nala_core.version())"` prints "0.1.0"
- [ ] `pip install -e .` from `python-orchestrator/` installs cleanly
- [ ] All source files are under 100 lines (everything is stubs at this stage)
- [ ] `.gitignore` covers all generated artifacts
- [ ] `README.md` exists

## Files Created in This Mission

~35 files across the Rust workspace, Python package, dashboard stub, CI config, and scripts.

## Dependencies to Install First

```bash
# Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup component add rustfmt clippy

# Python
# Install Python 3.11+ from python.org or your package manager
pip install maturin
```

## Estimated Complexity

Medium. Mostly configuration and boilerplate. The tricky part is getting PyO3/Maturin working correctly — pay careful attention to the `crate-type = ["cdylib", "rlib"]` setting and the module name matching between Cargo.toml and the `#[pymodule]` macro.
