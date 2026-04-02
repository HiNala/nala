# Nala development environment setup script (Windows PowerShell)
# Run from project root: .\scripts\setup.ps1

$ErrorActionPreference = "Stop"

function Info($msg)  { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[OK] $msg" -ForegroundColor Green }
function Fail($msg)  { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

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
$parts = $pyver.Split(".")
if (($parts.Count -lt 2) -or ([int]$parts[0] -lt 3) -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
    Fail "Python 3.11+ required (found $pyver)"
}
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
if (-not (Test-Path ".venv")) {
    python -m venv .venv
} else {
    Info "Reusing existing .venv"
}
& .\.venv\Scripts\python -m pip install --upgrade pip --quiet

# ── Maturin + PyO3 bridge ──────────────────────────────────────────────────

Info "Building PyO3 bridge..."
& .\.venv\Scripts\python -m pip install maturin --quiet
Push-Location rust-core\nala-bridge
& ..\..\.venv\Scripts\maturin develop --release
if ($LASTEXITCODE -ne 0) { Fail "Maturin build failed" }
Pop-Location
Ok "PyO3 bridge built"

# ── Python orchestrator ────────────────────────────────────────────────────

Info "Installing Python orchestrator..."
Push-Location python-orchestrator
& ..\.venv\Scripts\python -m pip install -e . --quiet
Pop-Location
Ok "Python orchestrator installed"

# ── Summary ────────────────────────────────────────────────────────────────

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To start Nala:"
Write-Host "  .\.venv\Scripts\Activate"
Write-Host "  .\rust-core\target\release\nala.exe"
Write-Host ""
Write-Host "Installing global commands (hinala, HiNala, nala)..."

$binDir = Join-Path $HOME ".hinala\bin"
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
$repoRoot = (Resolve-Path ".").Path

$launcherPath = Join-Path $binDir "hinala.cmd"
$launcherContent = @"
@echo off
setlocal
set "_HINALA_REPO=$repoRoot"
if exist "%_HINALA_REPO%\rust-core\target\release\hinala.exe" (
  set "_HINALA_EXE=%_HINALA_REPO%\rust-core\target\release\hinala.exe"
) else (
  set "_HINALA_EXE=%_HINALA_REPO%\rust-core\target\release\nala.exe"
)
if exist "%_HINALA_EXE%" (
  "%_HINALA_EXE%" --path "%cd%" %*
) else (
  echo HiNala binary not found. Re-run scripts\setup.ps1 in the Nala repo.
  exit /b 1
)
"@
Set-Content -Path $launcherPath -Value $launcherContent -Encoding ASCII
Set-Content -Path (Join-Path $binDir "nala.cmd") -Value "@echo off`r`ncall `"%~dp0hinala.cmd`" %*" -Encoding ASCII

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
if ($userPath -notlike "*$binDir*") {
    $newPath = if ($userPath) { "$userPath;$binDir" } else { $binDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    if ($env:Path -notlike "*$binDir*") {
        $env:Path = "$env:Path;$binDir"
    }
    Ok "Added $binDir to user PATH (open a new terminal)."
} else {
    if ($env:Path -notlike "*$binDir*") {
        $env:Path = "$env:Path;$binDir"
    }
    Ok "User PATH already contains $binDir."
}

Ok "Global command installed. Open a new terminal, then run: HiNala"
