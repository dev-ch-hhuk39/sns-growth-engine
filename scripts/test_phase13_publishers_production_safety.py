#!/usr/bin/env python3
"""Verify publisher CLIs keep real posting behind confirm gates."""
from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable] + cmd, cwd=_ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    checks = []
    code, out = run(["scripts/publish_x_post.py", "--account-id", "night_scout", "--mock", "--dry-run"])
    checks.append(("x mock dry-run", code == 0 and "DRY_RUN" in out))
    code2, out2 = run(["scripts/publish_threads_post.py", "--account-id", "night_scout", "--mock", "--dry-run"])
    checks.append(("threads mock dry-run", code2 == 0 and "DRY_RUN" in out2))
    code3, out3 = run(["scripts/publish_x_post.py", "--account-id", "night_scout", "--no-dry-run"])
    checks.append(("x confirmなしpost BLOCKED", code3 == 1 and "BLOCKED" in out3))
    code4, out4 = run(["scripts/publish_threads_post.py", "--account-id", "beauty_account", "--mock", "--dry-run"])
    checks.append(("beauty BLOCKED", code4 == 1 and "BLOCKED" in out4))
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
