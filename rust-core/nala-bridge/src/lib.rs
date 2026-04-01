//! PyO3 bridge — the Rust-to-Python interface.
// PyO3's wrap_pyfunction! macro internally generates .into() calls on the
// error type; suppress the useless_conversion lint for the entire crate.
#![allow(clippy::useless_conversion)]
//!
//! Exposes Nala's Rust core (indexing, scanning, metrics) as a native
//! Python extension module called `nala_core`. The Python orchestrator
//! imports this module to call Rust-speed operations from Python.
//!
//! Built with Maturin. Run `maturin develop` in this directory (with a
//! Python venv active) to build and install the module.
//!
//! All complex types are serialised through JSON so Python always receives
//! plain dicts — no Rust struct lifetimes leak into Python.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

// ── Helpers ────────────────────────────────────────────────────────────────

fn py_err(e: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(e.to_string())
}

fn symbol_to_json(s: &nala_indexer::Symbol) -> serde_json::Value {
    serde_json::json!({
        "kind":       s.kind.to_string(),
        "name":       s.name,
        "file_path":  s.file_path,
        "start_line": s.start_line,
        "end_line":   s.end_line,
        "language":   s.language,
        "metadata":   s.metadata,
    })
}

// ── Module functions ───────────────────────────────────────────────────────

/// Return the version of the nala_core native module.
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Scan a project directory and return a JSON string with the scan result.
///
/// Python usage:
/// ```python
/// import nala_core, json
/// result = json.loads(nala_core.scan_project("/path/to/project"))
/// print(result["total_files"])
/// ```
#[pyfunction]
fn scan_project(path: &str) -> PyResult<String> {
    let result = nala_indexer::scan_project(std::path::Path::new(path))
        .map_err(py_err)?;

    let json = serde_json::json!({
        "total_files":    result.total_files,
        "changed_files":  result.changed_files.len(),
        "new_files":      result.new_files.len(),
        "deleted_count":  result.deleted_count,
        "scan_duration_ms": result.scan_duration.as_millis(),
    });

    Ok(json.to_string())
}

/// Index a project (scan + parse + symbol extraction) and return JSON.
///
/// The returned JSON includes the full symbol list so the Python graph
/// builder can populate Neo4j without a second Rust call.
///
/// Python usage:
/// ```python
/// import nala_core, json
/// result = json.loads(nala_core.index_project("/path/to/project"))
/// for sym in result["symbols"]:
///     print(sym["kind"], sym["name"], sym["file_path"])
/// ```
#[pyfunction]
fn index_project(path: &str) -> PyResult<String> {
    let result = nala_indexer::index_project(std::path::Path::new(path))
        .map_err(py_err)?;

    let symbols: Vec<_> = result.symbols.iter().map(symbol_to_json).collect();

    let json = serde_json::json!({
        "indexed_files":    result.indexed_files,
        "total_symbols":    result.total_symbols,
        "function_count":   result.function_count,
        "class_count":      result.class_count,
        "import_count":     result.import_count,
        "index_duration_ms": result.index_duration.as_millis(),
        "total_files":      result.scan_result.total_files,
        "symbols":          symbols,
    });

    Ok(json.to_string())
}

/// Return all symbols for a project as a JSON array.
///
/// Equivalent to `index_project(...)[\"symbols\"]` but returns only the
/// symbols list, which is more convenient when the caller only needs symbols.
#[pyfunction]
fn get_all_symbols(path: &str) -> PyResult<String> {
    let result = nala_indexer::index_project(std::path::Path::new(path))
        .map_err(py_err)?;

    let symbols: Vec<_> = result.symbols.iter().map(symbol_to_json).collect();
    serde_json::to_string(&symbols).map_err(py_err)
}

// ── Module definition ──────────────────────────────────────────────────────

/// The nala_core Python module.
///
/// This is the native extension module exposing Rust-speed operations to the
/// Python orchestrator. It is built with Maturin and importable as `nala_core`.
#[pymodule]
fn nala_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(scan_project, m)?)?;
    m.add_function(wrap_pyfunction!(index_project, m)?)?;
    m.add_function(wrap_pyfunction!(get_all_symbols, m)?)?;
    Ok(())
}
