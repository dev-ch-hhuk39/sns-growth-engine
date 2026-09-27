#!/usr/bin/env python3
"""Ensure an explicitly no-post runtime cannot enter the publishing reconciler."""

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/run_buffered_production_host.sh"

with tempfile.TemporaryDirectory(prefix="buffered-no-post-test-") as temp:
    runtime = Path(temp) / ".buffered-runtime"
    current = runtime / "current"
    (current / "scripts").mkdir(parents=True)
    (current / "scripts/reconcile_due_production_slots.py").touch()
    (current / ".production-release").write_text("test-release\n", encoding="utf-8")
    shared = runtime / "shared"
    shared.mkdir()
    env_file = shared / "runtime.env"
    env_file.write_text("BUFFERED_POSTING_ENABLED=false\n", encoding="utf-8")
    env_file.chmod(0o600)

    result = subprocess.run(
        [str(LAUNCHER), "--account-id", "night_scout", "--apply", "--confirm-reconcile"],
        cwd=ROOT,
        env={
            **os.environ,
            "BUFFERED_RUNTIME_ROOT": str(runtime),
            "BUFFERED_POSTING_ENABLED": "true",
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
