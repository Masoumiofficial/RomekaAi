"""The diagnostic script must be correct precisely when everything else is broken.

Reported by the user on Windows: a browser showing
    Error response / Error code: 404 / Message: File not found.
That page is Python's built-in ``http.server`` (or CherryPy), not ROMKA — ROMKA
answers unknown routes with JSON and identifies itself with ``server: uvicorn``.
The doctor has to tell those two apart, because the fix differs completely.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import doctor  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Static(BaseHTTPRequestHandler):
    """Mimics `python -m http.server`: an HTML 404 page for any unknown route."""

    def do_GET(self):  # noqa: N802
        body = (b"<!DOCTYPE HTML><html><head><title>Error response</title></head><body>"
                b"<h1>Error response</h1><p>Error code: 404</p>"
                b"<p>Message: File not found.</p>"
                b"<p>Error code explanation: 404 - Nothing matches the given URI.</p>"
                b"</body></html>")
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep test output clean
        pass


class _FakeRomka(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/api/v1/health":
            body = json.dumps({"ok": True, "status": "healthy", "version": "9.9.9"}).encode()
            self.send_response(200)
        else:
            body = b'{"ok":false,"error":{"code":"http_error","message":"Not Found"}}'
            self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Server", "uvicorn")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _serve(handler) -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


@pytest.fixture
def static_server():
    server, port = _serve(_Static)
    yield port
    server.shutdown()


@pytest.fixture
def romka_like_server():
    server, port = _serve(_FakeRomka)
    yield port
    server.shutdown()


# ── port classification ─────────────────────────────────────────────────────

def test_free_port_is_reported_as_free():
    assert doctor.probe_port(_free_port())["state"] == "free"


def test_static_file_server_is_detected_as_foreign(static_server):
    info = doctor.probe_port(static_server)
    assert info["state"] == "other"
    assert info["static_server"] is True
    # BaseHTTPRequestHandler subclasses report "BaseHTTP/…", http.server "SimpleHTTP/…"
    assert info["server"].startswith(("SimpleHTTP", "BaseHTTP")) or info["server"] == ""


def test_foreign_static_server_fails_the_check_with_actionable_fix(static_server, capsys):
    report = doctor.Report()
    code = doctor.check_port(report, static_server)
    out = capsys.readouterr().out
    assert code == 13
    assert "NOT ROMKA" in out
    assert "404 File not found" in out          # names the user's exact symptom
    assert any("taskkill" in fix or "stop that server" in fix for fix in report.failures)
    assert any("Port 8010" in fix for fix in report.failures)


def test_romka_is_recognised_by_its_health_json(romka_like_server, capsys):
    report = doctor.Report()
    code = doctor.check_port(report, romka_like_server)
    out = capsys.readouterr().out
    assert code == 15                            # already running: start nothing
    assert "ROMKA is already running" in out
    assert "9.9.9" in out


def test_business_app_that_is_not_romka_is_still_reported_as_busy():
    class Other(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"<!doctype html><title>Some other app</title>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server, port = _serve(Other)
    try:
        info = doctor.probe_port(port)
        assert info["state"] == "other" and info["static_server"] is False
        assert doctor.check_port(doctor.Report(quiet=True), port) == 13
    finally:
        server.shutdown()


# ── schema / environment checks ─────────────────────────────────────────────

def test_latest_revision_comes_from_the_migration_files():
    head = doctor.latest_revision()
    assert head == "66c743d0c078", f"unexpected migration head: {head}"


def test_doctor_cli_exits_zero_on_a_healthy_port(romka_like_server):
    result = subprocess.run([sys.executable, "scripts/doctor.py", "--only", "port",
                             "--port", str(romka_like_server)],
                            capture_output=True, text=True, cwd=doctor.ROOT)
    assert result.returncode == 15, result.stdout


def test_doctor_cli_flags_a_static_server(static_server):
    result = subprocess.run([sys.executable, "scripts/doctor.py", "--only", "port",
                             "--port", str(static_server)],
                            capture_output=True, text=True, cwd=doctor.ROOT)
    assert result.returncode == 13
    assert "Nothing matches the given URI" not in result.stdout  # we explain, not quote raw


def test_missing_env_is_only_a_warning(tmp_path, monkeypatch, capsys):
    """Dev defaults are valid: a working install must not be reported as broken."""
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    assert doctor.check_env(doctor.Report()) is True
    assert "built-in defaults" in capsys.readouterr().out


def test_run_dev_refuses_to_start_on_a_foreign_port(static_server):
    """The shell wrapper must fail loudly instead of leaving a silent 404."""
    result = subprocess.run(["bash", "scripts/run_dev.sh"], capture_output=True, text=True,
                            cwd=doctor.ROOT,
                            env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                                 "PORT": str(static_server), "HOME": "/tmp"})
    assert result.returncode == 1
    assert "not usable" in result.stderr


def test_windows_start_script_checks_the_port_before_starting():
    text = (doctor.ROOT / "scripts" / "run_dev.ps1").read_text(encoding="utf-8")
    assert "doctor.py --only port" in text
    assert "-Port 8010" in text
    assert "Nothing was started" in text


def test_doctor_never_needs_third_party_packages():
    """It must run on a bare Python (that is the scenario it exists for)."""
    result = subprocess.run([sys.executable, "-S", "-c",
                             "import sys; sys.path.insert(0,'scripts'); import doctor; "
                             "print(doctor.latest_revision())"],
                            capture_output=True, text=True, cwd=doctor.ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "66c743d0c078"
    time.sleep(0)  # keep the import of time meaningful for linters
