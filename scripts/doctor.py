#!/usr/bin/env python3
"""ROMKA doctor — explain why the browser shows the wrong thing.

Written with the standard library ONLY: it must still work when the virtualenv,
a dependency or the app itself is broken (that is exactly when you need it).

It answers four questions:
  1. is there a usable Python + .venv, and are the dependencies installed?
  2. is the database migrated to the latest revision?
  3. is the port free, or is something ELSE (e.g. `python -m http.server`)
     answering on it while ROMKA is not running?
  4. if ROMKA answers, is it healthy?

Exit codes
    0  everything needed to start looks fine (or ROMKA is already healthy)
   10  no usable virtualenv / dependencies
   11  database not created or not migrated
   13  port occupied by something that is NOT ROMKA
   15  port occupied by ROMKA and it is already running

Usage
    python scripts/doctor.py
    python scripts/doctor.py --port 8000
    python scripts/doctor.py --only port --port 8000
    python scripts/doctor.py --only port --port 8000 --quiet   # for run_dev
    python scripts/doctor.py --only port --port 8000 --stop-owner   # asks first
    python scripts/doctor.py --only port --port 8000 --stop-owner --yes

``--stop-owner`` exists because documentation that says "``taskkill /PID
<your-pid> /F``" is a trap: PowerShell parses ``<`` as redirection ("The '<'
operator is reserved for future use"). The tool finds the PID itself and refuses
to kill anything that is not the process actually listening on that port, never
touches ROMKA/uvicorn, never touches system processes or its own process tree,
and asks for confirmation unless ``--yes`` is given in a non-interactive run.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OK, WARN, BAD, INFO = "[ OK ]", "[WARN]", "[FAIL]", "[ -- ]"
STATIC_SERVER_HINTS = (
    "nothing matches the given uri",   # python -m http.server
    "error response",                  # stdlib error page
    "directory listing for",           # stdlib index page
    "cheroot",                         # cherrypy
)


class Report:
    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet
        self.failures: list[str] = []

    def line(self, status: str, title: str, detail: str = "") -> None:
        if self.quiet and status == OK:
            return
        print(f"{status} {title}" + (f"\n       {detail}" if detail else ""))

    def fail(self, title: str, detail: str, fixes: list[str]) -> None:
        self.line(BAD, title, detail)
        self.failures.extend(fixes)


def check_venv(rep: Report) -> bool:
    exe = ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
    venv_python = ROOT / exe
    rep.line(INFO, "interpreter", f"{sys.executable} ({platform.python_version()})")
    if not venv_python.exists():
        rep.fail("virtualenv missing", f"expected {venv_python}",
                 ["run the setup script:  .\\scripts\\setup.ps1   or   ./scripts/setup.sh"])
        return False
    rep.line(OK, "virtualenv", str(venv_python))
    probe = subprocess.run(
        [str(venv_python), "-c",
         "import fastapi, uvicorn, sqlalchemy, alembic, dateutil, pydantic_settings;"
         "print(fastapi.__version__)"],
        capture_output=True, text=True)
    if probe.returncode != 0:
        rep.fail("dependencies missing inside .venv", probe.stderr.strip().splitlines()[-1]
                 if probe.stderr.strip() else "import failed",
                 ["install them:  .venv\\Scripts\\pip install -r requirements-dev.txt",
                  "  (Linux/macOS: .venv/bin/pip install -r requirements-dev.txt)"])
        return False
    rep.line(OK, "dependencies", f"fastapi {probe.stdout.strip()}")
    return True


def _env_value(name: str) -> str:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return ""
    for raw in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line.startswith(f"{name}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    return ""


def check_env(rep: Report) -> bool:
    """``.env`` is a convenience, not a requirement: Settings ships dev defaults."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        rep.line(WARN, ".env missing",
                 "running on built-in defaults (fine for dev; run the setup script to "
                 "create .env for GapGPT/Telegram settings)")
        return True
    rep.line(OK, ".env", f"database={_env_value('DATABASE_URL') or 'sqlite:///./romka.db'}")
    return True


def latest_revision() -> str:
    """Highest migration revision present on disk (by walking down_revision)."""
    versions = ROOT / "migrations" / "versions"
    revisions: dict[str, str | None] = {}
    for path in versions.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rev = re.search(r"^revision(?::\s*str)?\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision(?::[^=]+)?\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", text, re.M)
        if rev:
            revisions[rev.group(1)] = down.group(1) if down and down.group(1) else None
    if not revisions:
        return ""
    children = {d for d in revisions.values() if d}
    heads = [r for r in revisions if r not in children]
    return heads[0] if len(heads) == 1 else (heads[0] if heads else "")


def check_db(rep: Report) -> bool:
    url = _env_value("DATABASE_URL") or "sqlite:///./romka.db"
    if not url.startswith("sqlite"):
        rep.line(WARN, "database", f"{url.split('://')[0]} — connectivity is not checked here")
        return True
    path = ROOT / url.replace("sqlite:///", "").replace("sqlite://", "")
    if not path.exists():
        rep.fail("database file missing", str(path),
                 ["create + migrate:  alembic upgrade head   (or rerun the setup script)"])
        return False
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        row = con.execute("select version_num from alembic_version").fetchone()
        con.close()
    except sqlite3.Error as exc:
        rep.fail("database is not migrated", f"{path}: {exc}",
                 ["run:  alembic upgrade head"])
        return False
    current, head = (row[0] if row else ""), latest_revision()
    if head and current != head:
        rep.fail("database schema is out of date", f"db={current or '(empty)'} latest={head}",
                 ["run:  alembic upgrade head"])
        return False
    rep.line(OK, "database", f"{path.name} @ {current or 'empty'}")
    return True


def _owning_pid_number(port: int) -> int | None:
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                    return int(parts[4])
        else:
            out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                if f":{port} " in line:
                    match = re.search(r"pid=(\d+)", line)
                    if match:
                        return int(match.group(1))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def process_details(pid: int) -> dict:
    """Name + command line of a PID, using only what the OS already provides."""
    details: dict = {"pid": pid, "name": "", "cmdline": ""}
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True).stdout.strip()
            if out and "," in out:
                details["name"] = out.split(",")[0].strip('"')
            wmic = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/value"],
                capture_output=True, text=True).stdout
            if "CommandLine=" in wmic:
                details["cmdline"] = wmic.split("CommandLine=", 1)[1].strip()
        else:
            cmdline = Path(f"/proc/{pid}/cmdline")
            if cmdline.exists():
                details["cmdline"] = cmdline.read_bytes().replace(b"\x00", b" ").decode(
                    "utf-8", errors="ignore").strip()
            comm = Path(f"/proc/{pid}/comm")
            if comm.exists():
                details["name"] = comm.read_text(encoding="utf-8", errors="ignore").strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return details


PROTECTED_PIDS = {0, 1, 4}
# Marker matching is deliberately narrow. A bare "romka" must NOT be a marker:
# the project folder is usually called romka (e.g. C:\romka), so every process
# started from inside it - including an innocent `python -m http.server` - would
# look like ROMKA and the tool would refuse to free the port.
ROMKA_CMD_MARKERS = ("uvicorn", "app.main:app", "romka-dev", "run_dev.sh", "run_dev.ps1")
ROMKA_NAMES = {"romka", "romka.exe", "romka-dev", "romka-dev.exe", "romka-server"}


def protected_reason(pid: int, details: dict) -> str:
    """Why this PID must NOT be killed by us (empty string = safe to stop)."""
    if pid in PROTECTED_PIDS or pid == os.getpid() or pid == os.getppid():
        return "system process, this tool, or its parent"
    name = str(details.get("name", "")).lower().strip()
    cmdline = str(details.get("cmdline", "")).lower()
    if name in ROMKA_NAMES or any(marker in cmdline for marker in ROMKA_CMD_MARKERS):
        return "it looks like ROMKA/uvicorn itself (use CTRL+C in its window instead)"
    if details.get("name", "").lower() in {"system", "init", "systemd", "sshd", "launchd"}:
        return f"{details['name']} is a system service"
    return ""


def stop_owner(port: int, *, assume_yes: bool) -> int:
    """Stop the process listening on ``port`` after explicit confirmation."""
    pid = _owning_pid_number(port)
    if pid is None:
        print(f"No listener found on port {port} (nothing to stop).")
        return 0
    details = process_details(pid)
    label = f"PID {pid} ({details.get('name') or 'unknown'})"
    reason = protected_reason(pid, details)
    if reason:
        print(f"Refusing to stop {label}: {reason}.")
        print("Close it yourself, or start ROMKA on another port: --port 8010")
        return 14
    print(f"Process holding port {port}: {label}")
    if details.get("cmdline"):
        print(f"  command line: {details['cmdline'][:200]}")
    if not assume_yes:
        if not sys.stdin or not sys.stdin.isatty():
            print("Stopping a process needs confirmation; re-run with --yes to allow it.")
            return 14
        answer = input(f"Stop {label}? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled — nothing was stopped.")
            return 14
    try:
        if os.name == "nt":
            done = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                                  capture_output=True, text=True)
            if done.returncode != 0:
                print(f"taskkill failed: {(done.stderr or done.stdout).strip()}")
                return 14
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                time.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
            else:
                os.kill(pid, signal.SIGKILL)
        print(f"Stopped {label}. Port {port} should be free now.")
        return 0
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Could not stop {label}: {exc}")
        print("Close it manually, or start ROMKA on another port: --port 8010")
        return 14


def _owning_pid(port: int) -> str:
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                    pid = parts[4]
                    name = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                          capture_output=True, text=True).stdout
                    exe = name.splitlines()[3].split()[0] if len(name.splitlines()) > 3 else "?"
                    return f"PID {pid} ({exe})"
        else:
            out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                if f":{port} " in line:
                    match = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
                    if match:
                        return f"PID {match.group(2)} ({match.group(1)})"
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    return "unknown process"


def probe_port(port: int) -> dict:
    """Classify whatever answers on the port: romka | other | nothing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        if sock.connect_ex(("127.0.0.1", port)) != 0:
            return {"state": "free"}
    result: dict = {"state": "other", "server": "", "body": "", "pid": _owning_pid(port)}
    for path in ("/api/v1/health", "/auth"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as resp:
                result["server"] = resp.headers.get("server", "")
                result["body"] = resp.read(4000).decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:          # 404 etc. still tells us who answered
            result["server"] = exc.headers.get("server", "") if exc.headers else ""
            result["body"] = exc.read(4000).decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        if result["body"]:
            break
    try:
        payload = json.loads(result["body"])
        if isinstance(payload, dict) and "version" in payload:
            result.update(state="romka", health=payload)
            return result
    except (json.JSONDecodeError, TypeError):
        pass
    lowered = result["body"].lower()
    result["static_server"] = any(hint in lowered for hint in STATIC_SERVER_HINTS)
    return result


def check_port(rep: Report, port: int) -> int:
    info = probe_port(port)
    if info["state"] == "free":
        rep.line(OK, f"port {port}", "free — the server can bind")
        return 0
    if info["state"] == "romka":
        health = info.get("health", {})
        rep.line(OK, f"port {port}", f"ROMKA is already running (v{health.get('version')}, "
                                     f"{health.get('status')}) — just open "
                                     f"http://127.0.0.1:{port}/auth")
        return 15
    who = f"server header: {info['server'] or 'none'} · {info['pid']}"
    if info.get("static_server"):
        rep.fail(f"port {port} is answering, but it is NOT ROMKA",
                 f"a static file server (python -m http.server style) owns this port. {who}\n"
                 f"       That is why you saw '404 File not found': it looks for files, "
                 f"not for ROMKA routes such as /auth.",
                 ["free the port automatically (asks first):  "
                  f"powershell: .\\.venv\\Scripts\\python.exe scripts\\doctor.py "
                  f"--only port --port {port} --stop-owner",
                  "or close that server's window yourself (in PowerShell never paste an "
                  "angle-bracket placeholder into taskkill: '<' is a redirection operator)",
                  "then start ROMKA:  .\\scripts\\run_dev.ps1   (Linux/macOS: ./scripts/run_dev.sh)",
                  "or use another port:  .\\scripts\\run_dev.ps1 -Port 8010"])
        return 13
    rep.fail(f"port {port} is busy with another program",
             f"{who}",
             ["stop it, or start ROMKA on another port:  .\\scripts\\run_dev.ps1 -Port 8010",
              "  (Linux/macOS: PORT=8010 ./scripts/run_dev.sh)"])
    return 13


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diagnose a ROMKA install / port")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--only", choices=["all", "venv", "env", "db", "port"], default="all")
    ap.add_argument("--quiet", action="store_true", help="print only problems")
    ap.add_argument("--stop-owner", "--free-port", dest="stop_owner", action="store_true",
                    help="stop the process holding --port (asks first unless --yes)")
    ap.add_argument("--yes", action="store_true",
                    help="with --stop-owner: do not ask (needed in non-interactive runs)")
    args = ap.parse_args(argv)

    if args.stop_owner:
        info = probe_port(args.port)
        if info["state"] == "free":
            print(f"Port {args.port} is already free.")
            return 0
        if info["state"] == "romka":
            print(f"Port {args.port} is served by ROMKA already (v"
                  f"{info.get('health', {}).get('version')}) — nothing to stop.")
            return 15
        return stop_owner(args.port, assume_yes=args.yes)

    rep = Report(quiet=args.quiet)
    print(f"ROMKA doctor · {ROOT}")
    print(f"platform: {platform.system()} {platform.release()} · python {platform.python_version()}")
    print("-" * 64)

    codes: list[int] = []
    if args.only in ("all", "venv"):
        if not check_venv(rep):
            codes.append(10)
    if args.only in ("all", "env"):
        check_env(rep)
    if args.only in ("all", "db"):
        if not check_db(rep):
            codes.append(11)
    if args.only in ("all", "port"):
        codes.append(check_port(rep, args.port))

    codes = [c for c in codes if c]        # 0 means "this check passed"
    print("-" * 64)
    if not codes:
        print("Result: healthy. Open http://127.0.0.1:%d/auth" % args.port)
        return 0
    if codes == [15]:
        print("Result: ROMKA is already running — no need to start it again.")
        return 15
    if rep.failures:
        print("What to do:")
        for step in dict.fromkeys(rep.failures):
            print(f"  - {step}")
    else:
        print("Result: problems found (see above).")
    return codes[0]


if __name__ == "__main__":
    raise SystemExit(main())
