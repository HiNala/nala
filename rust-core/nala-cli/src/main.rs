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
        Some(Commands::Tui) | None => run_tui(&cli.path).await,
    }
}

// ── Command handlers ───────────────────────────────────────────────────────

async fn run_tui(path: &PathBuf) -> Result<()> {
    nala_tui::run(path).await
}

async fn run_scan(path: &PathBuf) -> Result<()> {
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

async fn run_index(path: &PathBuf) -> Result<()> {
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
