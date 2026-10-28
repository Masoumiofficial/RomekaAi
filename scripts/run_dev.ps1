param(
    [int]$Port = 8000,
    [switch]$NoReload
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "py" }

& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed" }

$args = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if (-not $NoReload) { $args += "--reload" }

Write-Host "ROMKA -> http://127.0.0.1:$Port/auth   (demo: demo@romka.local / RomkaDemo2026!)" -ForegroundColor Cyan
& $py @args
