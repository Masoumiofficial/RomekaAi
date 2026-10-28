"""The distributable archive itself is a deliverable — so it is tested.

Two real packaging bugs were found by extracting the archive and installing it
from scratch:
1. ``*.db-wal`` / ``*.db-shm`` sidecars (local SQLite state) were shipped;
2. the ``.env.*`` secret filter also dropped ``.env.example``, so a fresh
   install could not create its own ``.env`` at all.

These tests fail if either regression returns.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_release  # noqa: E402


@pytest.fixture(scope="module")
def archive(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("release") / "romka-test.zip"
    return build_release.build(out)


PREFIX = build_release.DEFAULT_PREFIX


def _names(archive: Path) -> set[str]:
    """Archive entries relative to the single top-level folder."""
    with zipfile.ZipFile(archive) as z:
        return {n.split("/", 1)[1] for n in z.namelist()
                if n.startswith(f"{PREFIX}/") and n != f"{PREFIX}/"}


def _all_entries(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as z:
        return z.namelist()


def test_archive_is_a_valid_non_empty_zip(archive):
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        names = z.namelist()
    assert len(names) > 100
    assert archive.stat().st_size > 100_000


@pytest.mark.parametrize("required", [
    "START_HERE.md", ".env.example", "requirements.txt", "requirements-dev.txt",
    "alembic.ini", "pyproject.toml", "app/main.py", "app/config.py",
    "migrations/env.py", "scripts/setup.sh", "scripts/setup.ps1",
    "scripts/run_dev.ps1", "scripts/run_dev.sh", "scripts/verify_provider.py", "scripts/doctor.py",
    "scripts/build_release.py", "tests/conftest.py", "docs/STATUS.md",
    "docs/AI-PROVIDERS.md", "docs/DEPLOYMENT.md", "deploy/nginx/romka.conf",
])
def test_archive_contains_what_a_fresh_install_needs(archive, required):
    assert required in _names(archive), f"{required} missing from the release archive"


def test_archive_never_ships_local_state_or_secrets(archive):
    names = _names(archive)
    for bad in (".env", ".romka_dev_secret", ".coverage", "romka.db"):
        assert bad not in names
    assert not [n for n in names if n.endswith((".db", ".db-wal", ".db-shm", ".pyc", ".log"))]
    assert not [n for n in names if n.startswith((".git/", ".venv/", "__pycache__/"))]


def test_archive_has_a_single_top_level_folder(archive):
    """Otherwise extracting scatters 130 files over the user's directory."""
    entries = _all_entries(archive)
    assert entries, "empty archive"
    top = {n.split("/", 1)[0] for n in entries}
    assert top == {PREFIX}, f"expected one root folder, found {sorted(top)[:5]}"
    assert f"{PREFIX}/START_HERE.md" in entries
    assert f"{PREFIX}/scripts/setup.ps1" in entries


PLACEHOLDERS = ("YOUR_", "CHANGE_ME", "CHANGEME", "PLACEHOLDER", "EXAMPLE", "XXX", "TODO")
ASSIGNMENT = re.compile(r"(?:AI_PRIMARY_API_KEY|AI_FALLBACK_API_KEY|GAPGPT_API_KEY|"
                        r"TELEGRAM_BOT_TOKEN|BALE_BOT_TOKEN)[ \t]*=[ \t]*"
                        r"([A-Za-z0-9_.:-]{12,})")
KEYLIKE = (re.compile(r"sk-[A-Za-z0-9]{20,}"),
           re.compile(r"\bbot\d{8,}:[A-Za-z0-9_-]{30,}"))


def _looks_like_placeholder(value: str) -> bool:
    upper = value.upper()
    return (any(tag in upper for tag in PLACEHOLDERS)
            or len(set(upper)) <= 2          # e.g. "xxxxxxxxxxxx"
            or upper.startswith("("))


def test_archive_has_no_embedded_credentials(archive):
    """Scan shipped text for what a leaked key would look like.

    Obvious placeholders from the templates (YOUR_GAPGPT_KEY, CHANGE_ME, ...) are
    allowed: the point is to catch a *real* value someone pasted into a file.
    """
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if name.endswith((".png", ".jpg", ".zip")):
                continue
            text = z.read(name).decode("utf-8", errors="ignore")
            for pattern in KEYLIKE:
                assert not pattern.search(text), f"possible credential in {name}"
            for match in ASSIGNMENT.finditer(text):
                value = match.group(1)
                assert _looks_like_placeholder(value), \
                    f"possible credential in {name}: {match.group(0)}"


def test_archive_build_is_deterministic(archive, tmp_path):
    """Same commit must give the same bytes, so a published sha256 is checkable."""
    again = build_release.build(tmp_path / "again.zip")
    assert hashlib.sha256(again.read_bytes()).hexdigest() == \
        hashlib.sha256(archive.read_bytes()).hexdigest()


def test_start_here_documents_the_real_demo_login_and_limits():
    text = (Path(build_release.ROOT) / "START_HERE.md").read_text(encoding="utf-8")
    settings = (Path(build_release.ROOT) / "app" / "config.py").read_text(encoding="utf-8")
    assert "demo@romka.local" in text
    assert "RomkaDemo2026!" in text
    assert 'ROMKA_DEMO_EMAIL: str = "demo@romka.local"' in settings
    # Honesty requirements: live verification and deployment must be marked undone.
    assert "تأیید زنده نیاز به کلید شما" in text
    assert "اجرا نشده" in text


def test_shipped_powershell_scripts_are_ascii_only():
    """Windows PowerShell 5.1 mis-decodes UTF-8 without BOM: keep .ps1 ASCII."""
    for path in (build_release.ROOT / "scripts").glob("*.ps1"):
        path.read_bytes().decode("ascii")  # raises UnicodeDecodeError if not ASCII


def test_builder_cli_reports_checksum(tmp_path):
    out = tmp_path / "out" / "romka.zip"
    result = subprocess.run([sys.executable, "scripts/build_release.py",
                             "--version", "0.0.0-test", "--out", str(out),
                             "--sha256-file"],
                            capture_output=True, text=True, cwd=build_release.ROOT)
    assert result.returncode == 0, result.stderr
    assert out.exists()
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    sidecar = out.with_suffix(".zip.sha256").read_text(encoding="utf-8")
    assert digest in sidecar and digest in result.stdout
