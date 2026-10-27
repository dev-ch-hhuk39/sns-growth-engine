#!/usr/bin/env python3
"""Ensure an explicitly no-post runtime cannot enter the publishing reconciler."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/run_buffered_production_host.sh"

with tempfile.TemporaryDirectory(prefix="buffered-no-post-test-") as temp:
    runtime = Path(temp).resolve() / ".buffered-runtime"
    current = runtime / "current"
    revision = "a" * 40
    release = runtime / "releases" / revision
    (release / "scripts").mkdir(parents=True)
    (release / "scripts/reconcile_due_production_slots.py").touch()
    (release / ".production-release").write_text(revision + "\n", encoding="utf-8")
    current.symlink_to(release)
    shared = runtime / "shared"
    shared.mkdir()
    env_file = shared / "runtime.env"
    env_file.write_text("BUFFERED_POSTING_ENABLED=false\n", encoding="utf-8")
    env_file.chmod(0o600)
    common_lock = Path(temp) / "deploy.lock"
    common_lock.touch(mode=0o600)
    launcher = Path(temp) / "host.sh"
    launcher.write_text(LAUNCHER.read_text().replace(
        "/run/lock/chadult-production-deploy.lock", str(common_lock)))
    launcher.chmod(0o700)
    mock_bin = Path(temp) / "bin"
    mock_bin.mkdir()
    for name, source in {
        "flock": "#!/bin/sh\nexit 0\n",
        "readlink": "#!" + sys.executable + "\nimport os,sys\nprint(os.path.realpath(sys.argv[2]))\n",
    }.items():
        executable = mock_bin / name
        executable.write_text(source)
        executable.chmod(0o700)

    result = subprocess.run(
        [str(launcher), "--account-id", "night_scout", "--apply", "--confirm-reconcile"],
        cwd=ROOT,
        env={
            **os.environ,
            "BUFFERED_RUNTIME_ROOT": str(runtime),
            "BUFFERED_RUNTIME_ENV_FILE": str(env_file),
            "BUFFERED_POSTING_ENABLED": "true",
            "PATH": str(mock_bin) + os.pathsep + os.environ["PATH"],
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "[SKIPPED] buffered production posting is disabled" in result.stdout
    assert "reconcile_due_production_slots.py" not in result.stdout
    assert "PUBLISH_ENABLED=true" not in result.stdout

print("buffered no-post runtime gate: PASS")
