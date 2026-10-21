#!/usr/bin/env python3
"""SNS-only Linux host smoke for a Python 3.11 + Pillow 13 immutable runtime.

This does not install/activate any production release or access Google Sheets,
tokens, databases, R2 objects or other VPS tools. It uses an auto-removed
temporary SNS-runner-owned directory and keeps the global deploy lock shared.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

import bootstrap_sns_python311 as bootstrap

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime")
LOCK = Path("/run/lock/chadult-production-deploy.lock")
MIN_PRE_FREE = 9 * 1024**3
MIN_POST_FREE = 8 * 1024**3
REVISION = "a" * 40


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def safe_process(args: list[str], *, env: dict[str, str], timeout: int,
                 reason: str) -> None:
    try:
        result = subprocess.run(
            ["nice", "-n", "15", *args],
            env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError(reason) from None
    require(result.returncode == 0, reason)


def guard_live_host() -> None:
    require(sys.platform == "linux" and os.uname().machine == "x86_64",
            "SNS_PY311_QA_REQUIRES_LINUX_X64")
    require(os.getuid() == pwd.getpwnam("snsrunner").pw_uid,
            "SNS_PY311_QA_REQUIRES_DEDICATED_OWNER")
    require(shutil.disk_usage("/").free >= MIN_PRE_FREE,
            "SNS_PY311_QA_STAGE_DISK_GATE")
    require(LOCK.is_file() and not LOCK.is_symlink(),
            "SNS_PY311_QA_SHARED_LOCK_UNAVAILABLE")
    for pointer in ("current", "previous"):
        link = ROOT / pointer
        require(link.is_symlink(), "SNS_PY311_QA_RECOVERY_POINTER_MISSING")
        target = link.resolve(strict=True)
        require(target.parent == ROOT / "releases"
                and (target / ".production-release").read_text().strip() == target.name
                and os.access(target / ".venv" / "bin" / "python", os.X_OK),
                "SNS_PY311_QA_LIVE_OR_PREVIOUS_UNHEALTHY")
    env = ROOT / "shared" / "runtime.env"
    require(env.is_file() and not env.is_symlink() and env.stat().st_mode & 0o777 == 0o600,
            "SNS_PY311_QA_PRIVATE_ENV_UNVERIFIABLE")
    # Match *whole key lines* without copying/printing any other secrets.
    keys = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(("BUFFERED_POSTING_ENABLED=", "SNS_P0_ONCE_GATE_ENABLED=")):
            key, value = line.split("=", 1)
            keys[key] = value
    require(keys == {
        "BUFFERED_POSTING_ENABLED": "false",
        "SNS_P0_ONCE_GATE_ENABLED": "false",
    }, "SNS_PY311_QA_POSTING_MUST_BE_DISABLED")


def main() -> int:
    try:
        guard_live_host()
        with LOCK.open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            with tempfile.TemporaryDirectory(
                prefix="sns-py311-disposable-", dir="/tmp"
            ) as folder:
                base = Path(folder)
                releases = base / "releases"
                releases.mkdir()
                stage = releases / (".stage-" + REVISION + ".ABC123")
                stage.mkdir()
                bootstrap.RELEASES = releases
                bootstrap.bootstrap(stage)
                venv = stage / ".venv"
                env = dict(os.environ)
                env.pop("LD_LIBRARY_PATH", None)
                env["PIP_NO_CACHE_DIR"] = "1"
                env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                for requirements in ("requirements.txt", "requirements-media-runtime.txt"):
                    print("SNS_QA_RESOLVE_AND_INSTALL=" + requirements, flush=True)
                    safe_process(
                        [str(venv / "bin" / "python"), "-m", "pip", "install",
                         "--quiet", "--only-binary=:all:", "--no-compile",
                         "-r", str(Path(__file__).resolve().parents[1] / requirements)],
                        env=env, timeout=250,
                        reason="SNS_PY311_QA_DEPENDENCY_INSTALL_FAILED_" + requirements.upper(),
                    )
                safe_process(
                    [str(venv / "bin" / "python"), "-m", "pip", "check"],
                    env=env, timeout=45,
                    reason="SNS_PY311_QA_DEPENDENCY_CONFLICT",
                )
                snippets = {
                    "PILLOW13": (
                        "import io; from PIL import Image; import PIL;"
                        "assert PIL.__version__=='13.0.0';"
                        "buf=io.BytesIO();Image.new('RGB',(12,12)).save(buf,'PNG');"
                        "buf.seek(0);assert Image.open(buf).size==(12,12)"
                    ),
                    "MEDIA_NATIVE": "import av,ctranslate2,onnxruntime,numpy",
                    "SHEETS_CLIENT": "import google.auth,gspread,requests,cryptography",
                    "PLAYWRIGHT": "import playwright.sync_api",
                }
                for label, script in snippets.items():
                    safe_process(
                        [str(venv / "bin" / "python"), "-c", script],
                        env=env, timeout=45,
                        reason="SNS_PY311_QA_IMPORT_FAILED_" + label,
                    )
                    print("SNS_QA_IMPORT=" + label + "_PASS", flush=True)
                require(shutil.disk_usage("/").free >= MIN_POST_FREE,
                        "SNS_PY311_QA_POST_STAGE_DISK_GATE")
            fcntl.flock(lock, fcntl.LOCK_UN)
        guard_live_host()
        print("SNS_PY311_PILLOW13_DISPOSABLE_FULL_QA=PASS")
    except (OSError, RuntimeError, bootstrap.BootstrapBlocked) as error:
        reason = str(error)
        if not reason.startswith("SNS_"):
            reason = "SNS_PY311_QA_UNVERIFIED_FAILURE"
        print(reason, file=sys.stderr)
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
