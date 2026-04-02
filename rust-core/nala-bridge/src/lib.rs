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

fn metrics_to_json(m: &nala_indexer::metrics::FileMetrics) -> serde_json::Value {
    serde_json::json!({
        "relative_path": m.relative_path,
        "language":      m.language,
        "ploc":          m.ploc,
        "sloc":          m.sloc,
        "cloc":          m.cloc,
        "blank":         m.blank,
        "cyclomatic":    m.cyclomatic,
        "functions":     m.function_complexity.iter().map(|f| serde_json::json!({
            "name":       f.name,
            "start_line": f.start_line,
            "end_line":   f.end_line,
            "cyclomatic": f.cyclomatic,
            "severity":   f.severity().to_string(),
        })).collect::<Vec<_>>(),
    })
}

/// Return the version of the nala_core native module.
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Scan a project directory and return a JSON string with the scan result.
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

/// Index a project (scan + parse + symbol extraction + metrics) and return JSON.
#[pyfunction]
fn index_project(path: &str) -> PyResult<String> {
    let result = nala_indexer::index_project(std::path::Path::new(path))
        .map_err(py_err)?;

    let symbols: Vec<_> = result.symbols.iter().map(symbol_to_json).collect();
    let metrics: Vec<_> = result.file_metrics.iter().map(metrics_to_json).collect();

    let json = serde_json::json!({
        "indexed_files":    result.indexed_files,
        "total_symbols":    result.total_symbols,
        "function_count":   result.function_count,
        "class_count":      result.class_count,
        "import_count":     result.import_count,
        "index_duration_ms": result.index_duration.as_millis(),
        "total_files":      result.scan_result.total_files,
        "symbols":          symbols,
        "file_metrics":     metrics,
    });

    Ok(json.to_string())
}

/// Return all symbols for a project as a JSON array.
#[pyfunction]
fn get_all_symbols(path: &str) -> PyResult<String> {
    let result = nala_indexer::index_project(std::path::Path::new(path))
        .map_err(py_err)?;

    let symbols: Vec<_> = result.symbols.iter().map(symbol_to_json).collect();
    serde_json::to_string(&symbols).map_err(py_err)
}

/// Compute code quality metrics for a project and return JSON.
#[pyfunction]
fn get_file_metrics(path: &str) -> PyResult<String> {
    let result = nala_indexer::index_project(std::path::Path::new(path))
        .map_err(py_err)?;

    let metrics: Vec<_> = result.file_metrics.iter().map(metrics_to_json).collect();
    serde_json::to_string(&metrics).map_err(py_err)
}

#[pymodule]
fn nala_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(scan_project, m)?)?;
    m.add_function(wrap_pyfunction!(index_project, m)?)?;
    m.add_function(wrap_pyfunction!(get_all_symbols, m)?)?;
    m.add_function(wrap_pyfunction!(get_file_metrics, m)?)?;
    Ok(())
}
