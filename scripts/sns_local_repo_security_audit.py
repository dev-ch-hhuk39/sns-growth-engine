#!/usr/bin/env python3
"""Mac-only replacement for CI's SCHEDULED pip-audit + git-history Gitleaks.

This is not a substitute for required GitHub PR-gate; it never edits repo,
Secrets, Sheets, SNS, R2, VPS or application configuration.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO = Path("/Users/hayatoa/Projects/sns-growth-engine-bank-acceptance-20261024")
STATE = Path.home() / ".cache" / "chadult-sns-repo-audit"
PYTHON = STATE / "venv/bin/python"
GITLEAKS = Path("/opt/homebrew/bin/gitleaks")
REQUIREMENTS = (
    "requirements.txt", "requirements-acquisition.txt",
    "requirements-media-runtime.txt", "requirements-ci.txt",
)
SECRET_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "COOKIE", "KEY", "CREDENTIAL", "AUTH", "PRIVATE")
ENV_BLOCK = frozenset({"PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_CONFIG_FILE", "GH_TOKEN", "GITHUB_TOKEN"})


def safe_environment() -> dict[str, str]:
    env = {
        k: v for k, v in os.environ.items()
        if k.upper() not in ENV_BLOCK and not any(mark in k.upper() for mark in SECRET_MARKERS)
    }
    env.update({
        "PUBLISH_ENABLED": "false",
        "ALLOW_REAL_THREADS_POST": "false",
        "ALLOW_REAL_X_POST": "false",
        "ALLOW_MEDIA_POSTS": "false",
        "ALLOW_VIDEO_DOWNLOAD": "false",
        "ALLOW_VIDEO_CUT": "false",
        "ALLOW_CLOUDINARY_UPLOAD": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
    })
    return env


def guarded_state() -> None:
    if REPO.is_symlink() or not (REPO / ".git").exists():
        raise RuntimeError("EXACT_REPO_NOT_AVAILABLE")
    if STATE.is_symlink() or not STATE.is_dir():
        raise RuntimeError("PRIVATE_STATE_UNAVAILABLE")
    mode = STATE.lstat().st_mode
    if not stat.S_ISDIR(mode) or mode & 0o077:
        raise RuntimeError("PRIVATE_STATE_PERMISSIONS")
    if not PYTHON.is_file() or not GITLEAKS.is_file():
        raise RuntimeError("PINNED_AUDIT_TOOLS_UNAVAILABLE")
    for filename in REQUIREMENTS:
        p = REPO / filename
        if not p.is_file() or p.is_symlink() or p.stat().st_size > 150_000:
            raise RuntimeError("REQUIREMENTS_SCOPE_INVALID")


def _temp_json() -> str:
    fd, path = tempfile.mkstemp(prefix=".sns-security.", suffix=".json", dir=STATE)
    os.fchmod(fd, 0o600)
    os.close(fd)
    return path


def audit_one(label: str, command: list[str], *, max_seconds: int) -> tuple[str, int]:
    report = _temp_json()
    try:
        # Commands receive no credentials; stderr is intentionally not printed
        # and leaks are 100% redacted by gitleaks, including private file.
        try:
            p = subprocess.run(
                command + [report],
                cwd=REPO, env=safe_environment(), capture_output=True,
                text=True, timeout=max_seconds, check=False,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT", -1
        try:
            data = json.loads(Path(report).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return "NO_VALID_REPORT", p.returncode
        if label == "pip_audit":
            if not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
                return "INVALID_REPORT", p.returncode
            vulnerable = sum(len(x.get("vulns", [])) for x in data["dependencies"]
                             if isinstance(x, dict) and isinstance(x.get("vulns", []), list))
            if p.returncode not in (0, 1):
                return "PROCESS_FAILED", p.returncode
            if bool(vulnerable) != bool(p.returncode):
                return "EXIT_COUNT_MISMATCH", p.returncode
            return ("VULNERABILITIES_FOUND" if vulnerable else "PASS"), vulnerable
        if label == "gitleaks":
            if not isinstance(data, list) or p.returncode not in (0, 2):
                return "INVALID_REPORT", p.returncode
            if bool(data) != (p.returncode == 2):
                return "EXIT_COUNT_MISMATCH", p.returncode
            return ("LEAKS_FOUND" if data else "PASS"), len(data)
        return "UNSUPPORTED_SCAN", p.returncode
    finally:
        Path(report).unlink(missing_ok=True)


def run() -> dict:
    os.umask(0o077)
    guarded_state()
    lock = STATE / ".security-audit.lock"
    if lock.is_symlink():
        raise RuntimeError("LOCK_SYMLINK")
    with lock.open("a+") as f:
        os.fchmod(f.fileno(), 0o600)
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        requirements = [part for name in REQUIREMENTS for part in ("-r", name)]
        pip_status, pip_count = audit_one(
            "pip_audit",
            [str(PYTHON), "-m", "pip_audit", "--format", "json",
             "--progress-spinner", "off", *requirements, "-o"],
            max_seconds=420,
        )
        git_status, git_count = audit_one(
            "gitleaks",
            [str(GITLEAKS), "git", "--no-banner", "--no-color",
             "--redact=100", "--exit-code=2", "--log-opts=--all",
             "--report-format=json", "--report-path"],
            max_seconds=180,
        )
        outcome = "PASS" if pip_status == "PASS" and git_status == "PASS" else "ATTENTION"
        result = {
            "status": outcome, "checked_at": datetime.now(timezone.utc).isoformat(),
            "pip_audit": {"status": pip_status, "vulnerability_records": pip_count},
            "gitleaks": {"status": git_status, "finding_count": git_count},
            "scope": "sns_repo_requirements_and_git_history",
            "github_actions_runs": 0, "paid_ai_calls": 0,
            "sns_posts": 0, "sheets_writes": 0, "vps_mutations": 0,
        }
        fd, tmp = tempfile.mkstemp(prefix=".security-result-", suffix=".tmp", dir=STATE)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, STATE / "latest.json")
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return result


def main() -> int:
    try:
        result = run()
    except Exception:
        result = {"status": "BLOCKED_UNVERIFIED", "sns_posts": 0,
                  "sheets_writes": 0, "github_actions_runs": 0}
    print("SNS_LOCAL_REPO_SECURITY=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
