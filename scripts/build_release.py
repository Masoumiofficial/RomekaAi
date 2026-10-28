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


def collect() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if not path.is_file() or path.name in SKIP_FILES or path.suffix in SKIP_SUFFIX:
            continue
        if path.name.startswith(SKIP_NAME_PREFIXES) or _is_secret_env(path.name):
            continue
        out.append((path, rel.as_posix()))
    assert out, "nothing to archive — wrong project root?"
    return out


def build(out_path: Path) -> Path:
    files = collect()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, arcname in files:
            info = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = path.suffix in {".sh", ".py"} or path.name in {"setup.sh"}
            info.external_attr = (0o755 if executable else 0o644) << 16
            archive.writestr(info, path.read_bytes())
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the ROMKA release zip")
    ap.add_argument("--version", default="0.2.0")
    ap.add_argument("--out", default="")
    ap.add_argument("--sha256-file", action="store_true", help="also write <zip>.sha256")
    args = ap.parse_args()

    out = Path(args.out) if args.out else ROOT / "release" / f"romka-v{args.version}.zip"
    build(out)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    size = out.stat().st_size
    print(f"archive : {out}")
    print(f"files   : {len(collect())}")
    print(f"size    : {size:,} bytes ({size / 1024:.1f} KiB)")
    print(f"sha256  : {digest}")
    if args.sha256_file:
        sidecar = out.with_suffix(out.suffix + ".sha256")
        sidecar.write_text(f"{digest}  {out.name}\n", encoding="utf-8")
        print(f"checksum: {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
