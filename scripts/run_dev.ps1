$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "py" }
& $py -m alembic upgrade head
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
