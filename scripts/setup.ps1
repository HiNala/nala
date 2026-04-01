# Nala development environment setup script (Windows PowerShell)
# Run from project root: .\scripts\setup.ps1

$ErrorActionPreference = "Stop"

function Info($msg)  { Write-Host "→ $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "✓ $msg" -ForegroundColor Green }
function Fail($msg)  { Write-Host "✗ $msg" -ForegroundColor Red; exit 1 }

Write-Host "`nNala Setup`n" -ForegroundColor White

# ── Prerequisites ──────────────────────────────────────────────────────────

Info "Checking prerequisites..."

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Fail "Rust not found. Install from https://rustup.rs"
}
Ok "Rust $(rustc --version)"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Fail "Python not found. Install Python 3.11+ from https://python.org"
}
$pyver = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Ok "Python $pyver"

# ── .env setup ─────────────────────────────────────────────────────────────

if (-not (Test-Path ".env")) {
    Info "Creating .env from .env.example..."
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "  Edit .env and add your API key:" -ForegroundColor Cyan
    Write-Host "    ANTHROPIC_API_KEY=sk-ant-..."
    Write-Host ""
}

# ── Rust build ─────────────────────────────────────────────────────────────

Info "Building Rust workspace..."
Push-Location rust-core
cargo build --release
if ($LASTEXITCODE -ne 0) { Fail "Rust build failed" }
Pop-Location
Ok "Rust workspace built"

# ── Python venv ────────────────────────────────────────────────────────────

Info "Creating Python virtualenv..."
python -m venv .venv
& .\.venv\Scripts\pip install --upgrade pip --quiet

# ── Maturin + PyO3 bridge ──────────────────────────────────────────────────

Info "Building PyO3 bridge..."
& .\.venv\Scripts\pip install maturin --quiet
Push-Location rust-core\nala-bridge
& ..\..\venv\Scripts\maturin develop --release
if ($LASTEXITCODE -ne 0) { Fail "Maturin build failed" }
Pop-Location
Ok "PyO3 bridge built"

# ── Python orchestrator ────────────────────────────────────────────────────

Info "Installing Python orchestrator..."
Push-Location python-orchestrator
& .\..\venv\Scripts\pip install -e . --quiet
Pop-Location
Ok "Python orchestrator installed"

# ── Summary ────────────────────────────────────────────────────────────────

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To start Nala:"
Write-Host "  .\.venv\Scripts\Activate"
Write-Host "  .\rust-core\target\release\nala.exe"
