//! Nala CLI entry point.
//!
//! Parses command-line arguments, initializes the runtime, and dispatches to
//! the appropriate subsystem (TUI, scan, index, etc.).

mod constants;

use anyhow::Result;
use clap::{Parser, Subcommand};
use constants::{APP_DESCRIPTION, APP_NAME, APP_VERSION};
use std::path::PathBuf;
use tracing::info;

// ── CLI definition ─────────────────────────────────────────────────────────

#[derive(Parser)]
#[command(
    name = APP_NAME,
    version = APP_VERSION,
    about = APP_DESCRIPTION,
    long_about = None,
)]
struct Cli {
    /// Project directory to operate on (defaults to current directory)
    #[arg(short, long, default_value = ".", global = true)]
    path: PathBuf,

    /// Enable verbose logging
    #[arg(short, long, global = true)]
    verbose: bool,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Scan project files and show what has changed since last scan
    Scan,

    /// Index the project: parse all source files and extract symbols
    Index,

    /// Launch the interactive terminal UI (default when no subcommand given)
    Tui,

    /// Start the optional web dashboard on localhost
    Dashboard {
        /// Port to listen on (default: 3000)
        #[arg(short, long, default_value_t = 3000)]
        port: u16,
    },
}

// ── Entry point ────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    init_logging(cli.verbose);

    info!("{} v{} starting", APP_NAME, APP_VERSION);

    match cli.command {
        Some(Commands::Scan) => run_scan(&cli.path).await,
        Some(Commands::Index) => run_index(&cli.path).await,
        Some(Commands::Dashboard { port }) => run_dashboard(&cli.path, port).await,
        Some(Commands::Tui) | None => run_tui(&cli.path).await,
    }
}

// ── Command handlers ───────────────────────────────────────────────────────

async fn run_tui(path: &std::path::Path) -> Result<()> {
    nala_tui::run(path).await
}

async fn run_scan(path: &std::path::Path) -> Result<()> {
    println!("Scanning {}...", path.display());
    let result = nala_indexer::scan_project(path)?;
    println!(
        "Found {} files ({} changed, {} new, {} deleted) in {:.2}s",
        result.total_files,
        result.changed_files.len(),
        result.new_files.len(),
        result.deleted_count,
        result.scan_duration.as_secs_f64()
    );
    Ok(())
}

async fn run_index(path: &std::path::Path) -> Result<()> {
    println!("Indexing {}...", path.display());
    let result = nala_indexer::index_project(path)?;
    println!(
        "Indexed {} symbols across {} files in {:.2}s",
        result.total_symbols,
        result.indexed_files,
        result.index_duration.as_secs_f64()
    );
    println!(
        "  Functions: {}  Classes: {}  Imports: {}",
        result.function_count, result.class_count, result.import_count
    );
    Ok(())
}

async fn run_dashboard(path: &std::path::Path, port: u16) -> Result<()> {
    let root_path = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    let mut root_for_env = root_path.to_string_lossy().to_string();
    #[cfg(windows)]
    {
        root_for_env = root_for_env.trim_start_matches(r"\\?\").to_string();
    }
    println!(
        "Starting Nala dashboard on http://127.0.0.1:{} (project: {})",
        port,
        root_for_env
    );
    println!("Press Ctrl+C to stop.");

    // Find the dashboard directory (repo-root/dashboard), anchored from current executable.
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()));

    let mut candidates: Vec<std::path::PathBuf> = Vec::new();
    if let Some(exe_dir) = exe_dir {
        candidates.push(exe_dir.join("..").join("..").join("..").join("dashboard"));
    }
    candidates.extend([
        std::path::PathBuf::from("dashboard"),
        std::path::PathBuf::from("../dashboard"),
        std::path::PathBuf::from("../../dashboard"),
    ]);
    let dashboard_dir = candidates
        .into_iter()
        .find(|p| p.join("server.py").exists())
        .unwrap_or_else(|| std::path::PathBuf::from("dashboard"));
    let dashboard_cwd = dashboard_dir
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(std::path::Path::new("."));

    let status = std::process::Command::new("python")
        .args([
            "-m",
            "uvicorn",
            "dashboard.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            &port.to_string(),
        ])
        .env("DASHBOARD_PORT", port.to_string())
        .env("NALA_PROJECT_ROOT", root_for_env)
        .current_dir(dashboard_cwd)
        .status();

    match status {
        Ok(s) if s.success() => Ok(()),
        Ok(s) => {
            anyhow::bail!("Dashboard process exited with code {}", s.code().unwrap_or(-1))
        }
        Err(e) => {
            eprintln!("Failed to start dashboard: {e}");
            eprintln!("Make sure uvicorn is installed: pip install uvicorn fastapi");
            Err(e.into())
        }
    }
}

// ── Helpers ────────────────────────────────────────────────────────────────

fn init_logging(verbose: bool) {
    use tracing_subscriber::{fmt, EnvFilter};
    let filter = if verbose {
        EnvFilter::new("debug")
    } else {
        EnvFilter::new("warn")
    };
    fmt().with_env_filter(filter).with_target(false).init();
}
