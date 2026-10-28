param(
    [int]$Port = 8000,
    [switch]$NoReload,
    [switch]$SkipChecks,
    [switch]$FreePort,
    [switch]$Yes
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "py" }

Write-Host "== ROMKA ==" -ForegroundColor Cyan
Write-Host "http://127.0.0.1:$Port/auth  (demo: demo@romka.local / RomkaDemo2026!)" -ForegroundColor DarkGray

# Never start silently on a port that another program already owns: that is how
# a browser ends up showing a 404 from `python -m http.server` instead of ROMKA.
$doctor = "scripts\doctor.py"
$hasDoctor = Test-Path $doctor
if (-not $SkipChecks -and -not $hasDoctor) {
    Write-Host "core build: port pre-flight is not included; starting directly." -ForegroundColor DarkGray
    Write-Host "If the port is busy, close the other program or run: .\scripts\run_dev.ps1 -Port 8010" -ForegroundColor DarkGray
}

if (-not $SkipChecks -and $hasDoctor) {
    & $py $doctor --only port --port $Port --quiet
    $code = $LASTEXITCODE

    if ($code -eq 15) {
        Write-Host ""
        Write-Host "ROMKA is already running on port $Port - opening it in your browser." -ForegroundColor Green
        Start-Process "http://127.0.0.1:$Port/auth"
        exit 0
    }

    if ($code -eq 13) {
        Write-Host ""
        if (-not $FreePort) {
            Write-Host "Port $Port is held by another program, so ROMKA cannot start." -ForegroundColor Red
            Write-Host "Nothing was started." -ForegroundColor Red
            Write-Host ""
            Write-Host "Options:" -ForegroundColor Yellow
            Write-Host "  1) let ROMKA free the port for you :  .\scripts\run_dev.ps1 -FreePort"
            Write-Host "  2) use a different port           :  .\scripts\run_dev.ps1 -Port 8010"
            Write-Host "  3) close that program yourself    :  stop the other window, then run again"
            Write-Host ""
            Write-Host "     (in PowerShell, never paste an angle-bracket placeholder into"
            Write-Host "      taskkill: '<' is a redirection operator and causes a ParserError)"
            Write-Host "     full diagnosis:  .\.venv\Scripts\python.exe scripts\doctor.py"
            exit 1
        }
        # -FreePort: the doctor finds the PID, refuses unsafe targets, and asks first.
        $args = @($doctor, "--only", "port", "--port", "$Port", "--stop-owner")
        if ($Yes) { $args += "--yes" }
        & $py @args
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Port $Port could not be freed. Nothing was started." -ForegroundColor Red
            Write-Host "Try another port:  .\scripts\run_dev.ps1 -Port 8010" -ForegroundColor Yellow
            exit 1
        }
        & $py $doctor --only port --port $Port --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Port $Port is still not usable. Nothing was started." -ForegroundColor Red
            exit 1
        }
    } elseif ($code -ne 0) {
        Write-Host ""
        Write-Host "Pre-flight check failed (exit $code). Nothing was started." -ForegroundColor Red
        Write-Host "Full diagnosis:  .\.venv\Scripts\python.exe scripts\doctor.py" -ForegroundColor Yellow
        Write-Host "(the 'core' download has no doctor; close the other program instead)" -ForegroundColor DarkGray
        exit 1
    }

    & $py -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed" }
} else {
    & $py -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed; server was not started" }
}

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if (-not $NoReload) { $uvicornArgs += "--reload" }

Start-Process "http://127.0.0.1:$Port/auth" -ErrorAction SilentlyContinue
& $py @uvicornArgs
