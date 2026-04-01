# Mission 06: PyO3 Bridge and Python Scaffold

## Objective

Complete the PyO3 bridge so the Python orchestrator can call all Rust core operations. Verify that `maturin develop` produces a working `nala_core` module and that the Python orchestrator installs cleanly.

## Status

**Core implementation in place.** See:
- `rust-core/nala-bridge/src/lib.rs` — PyO3 module with `version()`, `scan_project()`, `index_project()`
- `rust-core/nala-bridge/Cargo.toml` — `cdylib` crate type, PyO3 dependency
- `rust-core/nala-bridge/pyproject.toml` — Maturin build config
- `python-orchestrator/pyproject.toml` — Python package with all dependencies

## Remaining Work

### Extend the bridge with more APIs

Add to `nala-bridge/src/lib.rs`:

```rust
/// Get all symbols for a project as a JSON array.
#[pyfunction]
fn get_project_symbols(path: &str) -> PyResult<String> { ... }

/// Get metrics for a single file.
#[pyfunction]
fn get_file_metrics(path: &str) -> PyResult<String> { ... }

/// List all cached files with their languages and symbol counts.
#[pyfunction]
fn get_cached_files(project_root: &str) -> PyResult<String> { ... }
```

### Write Python bridge tests

In `python-orchestrator/tests/test_bridge.py`:
```python
import nala_core
import json

def test_version():
    assert nala_core.version() == "0.1.0"

def test_scan_project(tmp_path):
    (tmp_path / "test.rs").write_text("fn main() {}")
    result = json.loads(nala_core.scan_project(str(tmp_path)))
    assert result["total_files"] == 1
```

### Async bridge support

For streaming responses from the Python agent back to the Rust TUI, add a callback pattern or use tokio channels via pyo3-async-runtimes.

## Acceptance Criteria

- [ ] `maturin develop` builds without errors
- [ ] `python -c "import nala_core; print(nala_core.version())"` works
- [ ] `scan_project()` returns valid JSON from Python
- [ ] `index_project()` returns symbol counts from Python
- [ ] Bridge tests pass
- [ ] Python orchestrator installs with `pip install -e .`
