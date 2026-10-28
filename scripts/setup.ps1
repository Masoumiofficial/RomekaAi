# ROMKA local setup (Windows PowerShell 5.1+ / PowerShell 7).
# ASCII-only on purpose: Persian text in .ps1 breaks under legacy code pages.
# Usage:
#   .\scripts\setup.ps1              # create venv, install deps, migrate, verify
#   .\scripts\setup.ps1 -SkipTests   # faster: no test run
#   .\scripts\setup.ps1 -PythonExe "py -3.11"
param(
    [string]$PythonExe = "",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "== ROMKA setup ==" -ForegroundColor Cyan
Write-Host "project: $root"

function Resolve-Python {
    param([string]$Exe)
    if ($Exe) { return $Exe }
    foreach ($candidate in @("py -3.12", "py -3.11", "python")) {
        try {
            $parts = $candidate.Split(" ")
            $ver = & $parts[0] $parts[1..($parts.Length - 1)] --version 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver -match "3\.(11|12|13)") {
                Write-Host "python: $candidate ($ver)" -ForegroundColor Green
                return $candidate
            }
        } catch { }
    }
    throw "Python 3.11+ not found. Install it from python.org and enable 'Add python.exe to PATH'."
}

$py = Resolve-Python $PythonExe

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "creating virtual environment..." -ForegroundColor Yellow
    $parts = $py.Split(" ")
    & $parts[0] $parts[1..($parts.Length - 1)] -m venv .venv
} else {
    Write-Host "reusing existing .venv" -ForegroundColor DarkGray
}

$vpy = Join-Path $root ".venv\Scripts\python.exe"
Write-Host "installing dependencies..." -ForegroundColor Yellow
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r requirements-dev.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "dependency installation failed" }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "created .env from .env.example (dev defaults, demo account enabled)" -ForegroundColor Green
}

Write-Host "applying database migrations..." -ForegroundColor Yellow
& $vpy -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed" }

if (-not $SkipTests) {
    Write-Host "running the test suite (no network, no API key needed)..." -ForegroundColor Yellow
    & $vpy -m pytest -q
    if ($LASTEXITCODE -ne 0) { Write-Host "TESTS FAILED - see output above" -ForegroundColor Red; exit 1 }
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  start:  .\scripts\run_dev.ps1"
Write-Host "  open :  http://127.0.0.1:8000/auth"
Write-Host "  demo :  demo@romka.local / RomkaDemo2026!   (development only)"
Write-Host ""
Write-Host "Optional hosted model (GapGPT):"
if (Test-Path "scripts\verify_provider.py") {
    Write-Host "  `$env:GAPGPT_API_KEY=\"...\"; .\.venv\Scripts\python.exe scripts\verify_provider.py"
} else {
    Write-Host "  set GAPGPT_API_KEY in .env and switch AI_PRIMARY_PROVIDER; this ""core"" build"
    Write-Host "  ships without scripts/verify_provider.py."
}
