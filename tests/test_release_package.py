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


def _tree_profile() -> str:
    """Which profile this *tree* can produce.

    A "core" download has no ``scripts/doctor.py`` (removed on purpose, see
    ``PROFILE_EXCLUDES``). Detecting it keeps the suite green when a user runs
    ``pytest`` inside the core archive instead of the full one.
    """
    return "core" if not (build_release.ROOT / "scripts" / "doctor.py").exists() else "full"


TREE_PROFILE = _tree_profile()


@pytest.fixture(scope="module")
def archive(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("release") / "romka-test.zip"
    return build_release.build(out, profile=TREE_PROFILE)


@pytest.fixture(scope="module")
def core_archive(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("release-core") / "romka-core.zip"
    return build_release.build(out, profile="core")


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
    "docs/AI-PROVIDERS.md", "docs/DEPLOYMENT.md", "docs/ANTIVIRUS.md",
    "docs/TROUBLESHOOTING.md", "deploy/nginx/romka.conf",
])
def test_archive_contains_what_a_fresh_install_needs(archive, required):
    names = _names(archive)
    if required not in names and _excluded_by(TREE_PROFILE, required):
        pytest.skip(f"{required} is intentionally absent from the {TREE_PROFILE} profile")
    assert required in names, f"{required} missing from the release archive"


def _excluded_by(profile: str, name: str) -> bool:
    return any(name == e or name.startswith(e)
               for e in build_release.PROFILE_EXCLUDES[profile])


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


# --- "core" profile: the antivirus-friendly download -------------------------
# The full archive is plain text too (no .exe anywhere), yet scanners flag
# process-killing / key-reading helpers. The core profile removes exactly those
# and nothing the product needs to start.

CORE_REMOVED = ("scripts/doctor.py", "scripts/verify_provider.py", "tests/test_doctor.py")


def test_core_profile_drops_the_scanner_sensitive_helpers(core_archive):
    names = _names(core_archive)
    for gone in CORE_REMOVED:
        assert gone not in names, f"{gone} must not ship in the core profile"
    assert not [n for n in names if n.startswith("deploy/")]


def test_core_profile_is_still_a_complete_install(core_archive):
    names = _names(core_archive)
    for kept in ("START_HERE.md", "README.md", ".env.example", "requirements.txt",
                 "alembic.ini", "app/main.py", "app/config.py", "migrations/env.py",
                 "scripts/setup.sh", "scripts/setup.ps1",
                 "scripts/run_dev.sh", "scripts/run_dev.ps1",
                 "scripts/build_release.py", "docs/ANTIVIRUS.md",
                 "app/web/templates/base.html"):
        assert kept in names, f"{kept} missing from the core profile"
    # No executables at all, in either profile: that is the point of the answer
    # to "why does my antivirus complain".
    assert not [n for n in names if n.lower().endswith((".exe", ".dll", ".msi", ".scr", ".pyd"))]


def test_run_scripts_survive_a_missing_doctor():
    """Core has no doctor.py, so the run scripts must not call it unconditionally."""
    sh = (build_release.ROOT / "scripts" / "run_dev.sh").read_text(encoding="utf-8")
    ps1 = (build_release.ROOT / "scripts" / "run_dev.ps1").read_text(encoding="utf-8")
    assert "HAVE_DOCTOR" in sh
    assert "doctor.py" in sh.split("HAVE_DOCTOR", 1)[1]
    assert "hasDoctor" in ps1
    # and the PowerShell one must still be ASCII for Windows PowerShell 5.1
    ps1.encode("ascii")


# --- published checksums: one file, no second download ----------------------
# A user verified the zip, then got "Cannot find path ... .sha256" because the
# sidecar is a *separate* download. downloads/CHECKSUMS.txt can be read straight
# from the GitHub web page, so it must exist and must describe what is published.

def test_builder_defaults_to_the_version_the_code_reports(tmp_path):
    sys.path.insert(0, str(Path(build_release.ROOT)))
    from app import __version__ as code_version
    out = tmp_path / "romka.zip"
    result = subprocess.run([sys.executable, "scripts/build_release.py", "--out", str(out)],
                            capture_output=True, text=True, cwd=build_release.ROOT)
    assert result.returncode == 0, result.stderr
    assert build_release.project_version() == code_version
    assert out.exists()


def test_published_checksums_file_matches_the_published_archives():
    downloads = Path(build_release.ROOT) / "downloads"
    zips = sorted(downloads.glob("*.zip"))
    if not zips:
        pytest.skip("no published archives in this tree")
    text = (downloads / "CHECKSUMS.txt").read_text(encoding="utf-8")
    listed = set(re.findall(r"\b([0-9a-f]{64})\b", text))
    for zip_path in zips:
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        assert digest in listed, f"{zip_path.name} is published but its sha256 is not in CHECKSUMS.txt"
        assert zip_path.name in text, f"{zip_path.name} is not named in CHECKSUMS.txt"


def test_published_archives_are_the_current_version():
    """A stale download is worse than none: it cannot be reproduced from HEAD."""
    from app import __version__ as code_version
    for zip_path in (Path(build_release.ROOT) / "downloads").glob("*.zip"):
        assert code_version in zip_path.name, f"{zip_path.name} is not v{code_version}"


def test_shipped_docs_never_ask_the_user_to_weaken_execution_policy():
    """Telling users to switch the PowerShell policy off is bad practice *and* a
    detection magnet.

    Defender flagged ``START_HERE.md`` itself (the docs, not code). We cannot
    diagnose their scanner from here, so we remove the one pattern in our text
    that genuinely looks like malware: telling users to switch the PowerShell
    execution policy off. ``Unblock-File`` removes the downloaded-file mark and
    keeps RemoteSigned in force.
    """
    policy = re.compile(r"ExecutionPolicy[^\n]{0,40}Bypass")
    offenders = []
    for path in list(build_release.ROOT.glob("*.md")) + \
            list((build_release.ROOT / "docs").rglob("*.md")) + \
            list((build_release.ROOT / "scripts").glob("*.*")):
        if path.suffix not in {".md", ".ps1", ".sh"}:
            continue
        for match in policy.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(f"{path.name}: {match.group(0)[:60]}")
    assert not offenders, offenders


def test_start_here_stays_a_clean_quick_start():
    """Defender flagged START_HERE.md itself (Trojan:Script/Sabsik.FL.A!ml).

    A quick-start file should be short and free of process-killing commands; the
    diagnosis material lives in docs/TROUBLESHOOTING.md, which is where the
    'kill the port owner' instructions belong.
    """
    text = (build_release.ROOT / "START_HERE.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 160, "START_HERE.md is drifting back into a manual"
    assert "docs/TROUBLESHOOTING.md" in text
    assert "docs/ANTIVIRUS.md" in text
    for scary in ("taskkill", "Stop-Process", "Get-NetTCPConnection", "ExecutionPolicy",
                  "netstat", "kill -9"):
        assert scary not in text, f"{scary} belongs in docs/TROUBLESHOOTING.md"


def test_troubleshooting_keeps_the_hard_won_lessons():
    text = (build_release.ROOT / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")
    assert "$ownerPid" in text                      # $PID is read-only in PowerShell
    assert "operator is reserved" in text           # the '<' placeholder trap
    assert "-FreePort" in text
    assert "server: uvicorn" in text                # how to tell whose 404 this is


def test_windows_setup_accepts_any_supported_python_version():
    """A user with Python 3.13/3.14 was told 'Python 3.11+ not found'.

    Two real bugs: the probe only accepted 3.11-3.13 (pyproject says >=3.11), and
    '$parts[1..($parts.Length - 1)]' turned a one-word command ('python') into a
    bogus argument list, so the fallback could never work.
    """
    text = (build_release.ROOT / "scripts" / "setup.ps1").read_text(encoding="utf-8")
    assert "$MinimumMinor = 11" in text
    assert '3\\.(11|12|13)' not in text, "version gate is too narrow again"
    for candidate in ('"py -3.13"', '"py -3.14"', '"py -3"', '"python"'):
        assert candidate in text, f"{candidate} missing from the probe list"
    assert "did not answer --version" in text      # explicit -PythonExe is validated
    assert "-PythonExe" in text
    assert "$parts.Length" not in text, "fragile array slice is back"
