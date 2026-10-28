param(
    [int]$Port = 8000,
    [switch]$NoReload,
    [switch]$SkipChecks
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "py" }

Write-Host "== ROMKA ==" -ForegroundColor Cyan
Write-Host "https://127.0.0.1:$Port/auth  (demo: demo@romka.local / RomkaDemo2026!)" -ForegroundColor DarkGray

# Never start silently on a port that another program already owns: that is how
# a browser ends up showing a 404 from `python -m http.server` instead of ROMKA.
if (-not $SkipChecks) {
    & $py scripts\doctor.py --only port --port $Port
    $code = $LASTEXITCODE
    if ($code -eq 15) {
        Write-Host ""
        Write-Host "ROMKA is already running on port $Port - opening it in your browser." -ForegroundColor Green
        Start-Process "http://127.0.0.1:$Port/auth"
        exit 0
    }
    if ($code -ne 0) {
        Write-Host ""
        Write-Host "Port $Port is not usable (exit $code). Nothing was started." -ForegroundColor Red
        Write-Host "Try a different port:  .\scripts\run_dev.ps1 -Port 8010" -ForegroundColor Yellow
        Write-Host "Full diagnosis     :  .\.venv\Scripts\python.exe scripts\doctor.py" -ForegroundColor Yellow
        exit 1
    }
    & $py -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed" }
} else {
    & $py -m alembic upgrade head
}

$args = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if (-not $NoReload) { $args += "--reload" }

Start-Process "http://127.0.0.1:$Port/auth" -ErrorAction SilentlyContinue
& $py @args
