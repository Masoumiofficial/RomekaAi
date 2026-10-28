#!/usr/bin/env python3
"""Build the distributable source archive for a ROMKA release.

Deterministic on purpose: fixed timestamps and sorted input, so rebuilding the
same commit gives the same bytes (verifiable sha256).

Excludes secrets and local state by default: .git, .venv, .env, romka.db,
.romka_dev_secret, caches and any *.db/*.log file.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
             ".mypy_cache", "dist", "build", "backups", "release", "node_modules",
             # published build output lives here; must never be re-archived
             "downloads"}
SKIP_FILES = {"romka.db", ".env", ".romka_dev_secret", ".coverage", "coverage.xml"}
SKIP_SUFFIX = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".log"}
# Any SQLite sidecar (romka.db-wal, romka.db-shm, *.db-journal) is LOCAL STATE.
SKIP_NAME_PREFIXES = ("romka.db", ".romka_dev_secret")
# .env.* may be a real secret file — but *.example templates MUST ship, otherwise a
# fresh install cannot create its own .env (caught by an end-to-end extract test).
ENV_KEEP_SUFFIXES = (".example", ".sample", ".template")


def _is_secret_env(name: str) -> bool:
    if name == ".env":
        return True
    if not name.startswith(".env"):
        return False
    return not name.endswith(ENV_KEEP_SUFFIXES)
FIXED_TIME = (2026, 10, 28, 0, 0, 0)
DEFAULT_PREFIX = "romka"

# Some antivirus engines flag automation helpers that enumerate processes, stop
# them, or read API keys from the environment - even in plain, readable source.
# The "core" profile ships the same product without those helpers, so a user can
# install and run ROMKA with nothing that looks like a PUP to a scanner.
PROFILE_EXCLUDES: dict[str, tuple[str, ...]] = {
    "full": (),
    "core": (
        "scripts/doctor.py",          # process enumeration + taskkill + port probing
        "scripts/verify_provider.py",  # reads an API key from env and posts it out
        "tests/test_doctor.py",        # imports the excluded helper
        "deploy/",                     # systemd/nginx/backup shell automation
    ),
}


def collect(prefix: str = "", profile: str = "full") -> list[tuple[Path, str]]:
    excludes = PROFILE_EXCLUDES.get(profile)
    if excludes is None:
        raise SystemExit(f"unknown profile '{profile}' (choose from {sorted(PROFILE_EXCLUDES)})")
    out: list[tuple[Path, str]] = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if not path.is_file() or path.name in SKIP_FILES or path.suffix in SKIP_SUFFIX:
            continue
        if path.name.startswith(SKIP_NAME_PREFIXES) or _is_secret_env(path.name):
            continue
        posix = rel.as_posix()
        if any(posix == e or posix.startswith(e) for e in excludes):
            continue
        out.append((path, f"{prefix}/{rel.as_posix()}" if prefix else rel.as_posix()))
    assert out, "nothing to archive — wrong project root?"
    return out


def build(out_path: Path, prefix: str = DEFAULT_PREFIX, profile: str = "full") -> Path:
    """Build the archive. ``prefix`` puts everything under one folder.

    Without it, extracting the zip scatters 130 files into whatever directory the
    user is standing in (found by testing the real archive). With it,
    ``Expand-Archive -DestinationPath C:\\`` or ``unzip`` always yields ``romka/``.
    """
    files = collect(prefix, profile)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, arcname in files:
            info = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = path.suffix in {".sh", ".py"} or path.name in {"setup.sh"}
            info.external_attr = (0o755 if executable else 0o644) << 16
            archive.writestr(info, path.read_bytes())
    return out_path


def project_version() -> str:
    """Single source of truth: ``app/__init__.py``.

    A stale ``--version`` default once put the wrong number in a filename, so the
    flag now defaults to the version the code actually reports.
    """
    text = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("cannot read __version__ from app/__init__.py")
    return match.group(1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the ROMKA release zip")
    ap.add_argument("--version", default=None,
                    help="default: __version__ from app/__init__.py")
    ap.add_argument("--out", default="")
    ap.add_argument("--sha256-file", action="store_true", help="also write <zip>.sha256")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX,
                    help="single top-level folder inside the zip (default: romka; '' = none)")
    ap.add_argument("--profile", default="full", choices=sorted(PROFILE_EXCLUDES),
                    help="full = everything; core = no automation helpers that antivirus "
                         "heuristics may flag")
    args = ap.parse_args()
    if args.version is None:
        args.version = project_version()

    suffix = "" if args.profile == "full" else f"-{args.profile}"
    out = (Path(args.out) if args.out
           else ROOT / "release" / f"romka-v{args.version}{suffix}.zip")
    build(out, prefix=args.prefix, profile=args.profile)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    size = out.stat().st_size
    print(f"archive : {out}")
    print(f"profile : {args.profile}")
    print(f"files   : {len(collect(args.prefix, args.profile))}")
    print(f"size    : {size:,} bytes ({size / 1024:.1f} KiB)")
    print(f"sha256  : {digest}")
    if args.sha256_file:
        sidecar = out.with_suffix(out.suffix + ".sha256")
        sidecar.write_text(f"{digest}  {out.name}\n", encoding="utf-8")
        print(f"checksum: {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
