$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

Write-Host "HiNala benchmark (scan/index)" -ForegroundColor Cyan

$bin = Join-Path $root "rust-core\target\release\hinala.exe"
if (-not (Test-Path $bin)) {
    $bin = Join-Path $root "rust-core\target\release\nala.exe"
}
if (-not (Test-Path $bin)) {
    Write-Host "Release binary missing. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Command: $bin --path `"$root`" scan" -ForegroundColor Gray
Measure-Command { & $bin --path $root scan } | ForEach-Object {
    Write-Host ("Scan elapsed: {0:N2}s" -f $_.TotalSeconds) -ForegroundColor Green
}

Write-Host "Command: $bin --path `"$root`" index" -ForegroundColor Gray
Measure-Command { & $bin --path $root index } | ForEach-Object {
    Write-Host ("Index elapsed: {0:N2}s" -f $_.TotalSeconds) -ForegroundColor Green
}
