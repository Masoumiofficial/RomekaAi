# ROMKA local setup (Windows PowerShell 5.1+ / PowerShell 7).
# ASCII-only on purpose: Persian text in .ps1 breaks under legacy code pages.
# Usage:
#   .\scripts\setup.ps1              # create venv, install deps, migrate, verify
#   .\scripts\setup.ps1 -SkipTests   # faster: no test run
#   .\scripts\setup.ps1 -PythonExe "py -3.11"
#   .\scripts\setup.ps1 -RecreateVenv  # throw away a broken .venv and rebuild
param(
    [string]$PythonExe = "",
    [switch]$SkipTests,
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "== ROMKA setup ==" -ForegroundColor Cyan
Write-Host "project: $root"

$MinimumMinor = 11

# Probe one candidate ("py -3.13", "python", ...) and report what it really is.
# The old version only accepted 3.11/3.12/3.13, so a machine with Python 3.14 was
# told "Python 3.11+ not found" - a real bug reported by a user.
function Invoke-PythonProbe {
    param([string]$Candidate)
    $parts = @($Candidate.Trim().Split(" "))
    $cmd = $parts[0]
    $rest = @()
    if ($parts.Count -gt 1) { $rest = $parts[1..($parts.Count - 1)] }
    try {
        $out = & $cmd @rest --version 2>&1 | Out-String
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0) { return $null }
    $match = [regex]::Match($out, "Python\s+(\d+)\.(\d+)")
    if (-not $match.Success) { return $null }
    return [pscustomobject]@{
        Command = $Candidate
        Major   = [int]$match.Groups[1].Value
        Minor   = [int]$match.Groups[2].Value
        Raw     = $out.Trim()
    }
}

function Resolve-Python {
    param([string]$Exe)
    if ($Exe) {
        $probe = Invoke-PythonProbe $Exe
        if (-not $probe) { throw "-PythonExe '$Exe' did not answer --version. Check the path." }
        if ($probe.Major -ne 3 -or $probe.Minor -lt $MinimumMinor) {
            throw "-PythonExe '$Exe' is $($probe.Raw); Python 3.$MinimumMinor+ is required."
        }
        Write-Host "python: $Exe ($($probe.Raw))" -ForegroundColor Green
        return $Exe
    }
    $candidates = @("py -3.14", "py -3.13", "py -3.12", "py -3.11", "py -3", "python", "python3")
    $seen = @()
    foreach ($candidate in $candidates) {
        $probe = Invoke-PythonProbe $candidate
        if (-not $probe) { continue }
        $seen += "$candidate -> $($probe.Raw)"
        if ($probe.Major -eq 3 -and $probe.Minor -ge $MinimumMinor) {
            Write-Host "python: $candidate ($($probe.Raw))" -ForegroundColor Green
            return $candidate
        }
    }
    if ($seen.Count -gt 0) {
        throw ("Python 3.$MinimumMinor+ is required but only found: " + ($seen -join "; ") +
               ". Install a newer Python from https://www.python.org/downloads/windows/ " +
               "or point at the right one, e.g. .\scripts\setup.ps1 -PythonExe ""C:\Python313\python.exe""")
    }
    throw ("Python was not found on PATH. Install Python 3.11+ from " +
           "https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'), " +
           "then close and reopen PowerShell and run this script again. " +
           "If it is installed elsewhere: .\scripts\setup.ps1 -PythonExe ""C:\Python313\python.exe""")
}

$py = Resolve-Python $PythonExe

$venvDir = Join-Path $root ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$venvCfg = Join-Path $venvDir "pyvenv.cfg"

# A venv directory can exist and still be unusable: an interrupted creation, a
# half-deleted folder, or a moved/renamed project leaves python.exe without
# pyvenv.cfg, and every later command then dies with
#   "failed to locate pyvenv.cfg: The system cannot find the file specified."
# Testing only for python.exe wedged setup forever (reported by a user), so the
# venv is probed and rebuilt automatically.
function Test-VenvHealthy {
    param([string]$Dir, [string]$Py)
    if (-not (Test-Path $Py)) { return $false }
    if (-not (Test-Path (Join-Path $Dir "pyvenv.cfg"))) { return $false }
    try {
        & $Py -c "import sys" 2>&1 | Out-Null
    } catch {
        return $false
    }
    return ($LASTEXITCODE -eq 0)
}

function New-RomkaVenv {
    param([string]$Command, [string]$Dir)
    $parts = @($Command.Trim().Split(" "))
    $cmd = $parts[0]
    $rest = @()
    if ($parts.Count -gt 1) { $rest = $parts[1..($parts.Count - 1)] }
    & $cmd @rest -m venv $Dir
    if ($LASTEXITCODE -ne 0) { throw "could not create .venv with '$Command'" }
    if (-not (Test-Path (Join-Path $Dir "Scripts\python.exe"))) {
        throw ".venv was created but has no Scripts\python.exe"
    }
}

if ($RecreateVenv -and (Test-Path $venvDir)) {
    Write-Host "removing .venv (-RecreateVenv)..." -ForegroundColor Yellow
    Remove-Item $venvDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $venvDir) {
        throw ("could not delete $venvDir - close any running ROMKA/Python window, " +
               "then delete the folder manually and run setup again")
    }
}

if (-not (Test-Path $venvDir)) {
    Write-Host "creating virtual environment..." -ForegroundColor Yellow
    New-RomkaVenv $py $venvDir
} elseif (Test-VenvHealthy $venvDir $venvPy) {
    Write-Host "reusing existing .venv" -ForegroundColor DarkGray
} else {
    Write-Host "existing .venv is broken (missing pyvenv.cfg or python.exe does not run)" -ForegroundColor Yellow
    Write-Host "  rebuilding it; .env and the database are NOT touched" -ForegroundColor Yellow
    Remove-Item $venvDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $venvDir) {
        throw ("$venvDir is locked and cannot be removed - close every ROMKA/Python " +
               "window, then run: .\scripts\setup.ps1 -RecreateVenv")
    }
    New-RomkaVenv $py $venvDir
}

if (-not (Test-VenvHealthy $venvDir $venvPy)) {
    throw (".venv was created but this Python cannot run from it. Try a different " +
           "interpreter, e.g. .\scripts\setup.ps1 -RecreateVenv -PythonExe ""py -3.12""")
}

$vpy = $venvPy
Write-Host "installing dependencies..." -ForegroundColor Yellow
& $vpy -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "warning: could not upgrade pip (continuing)" -ForegroundColor DarkYellow }
& $vpy -m pip install -r requirements-dev.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "pip could not install the requirements (exit $LASTEXITCODE)." -ForegroundColor Red
    Write-Host "  network/SSL problem?  retry with a mirror:" -ForegroundColor Yellow
    Write-Host "    `$env:PIP_INDEX_URL=""https://mirror-pypi.runflare.com/simple""" -ForegroundColor Yellow
    Write-Host "    .\scripts\setup.ps1" -ForegroundColor Yellow
    Write-Host "  broken .venv?         .\scripts\setup.ps1 -RecreateVenv" -ForegroundColor Yellow
    throw "dependency installation failed"
}

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
