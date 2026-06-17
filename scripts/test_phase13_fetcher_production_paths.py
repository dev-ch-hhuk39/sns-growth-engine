#!/usr/bin/env python3
"""Smoke-test fetcher production CLI paths stay dry-run safe."""
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
    ok, out = run(["scripts/fetch_source_posts.py", "--account-id", "night_scout", "--platform", "x", "--mock", "--dry-run"])
    checks.append(("mock x dry-run", ok == 0 and "実取得をブロック" not in out))
    ok2, out2 = run(["scripts/fetch_source_posts.py", "--account-id", "night_scout", "--platform", "x", "--fetch", "--dry-run"])
    checks.append(("confirmなしfetch BLOCKED", ok2 == 1 and "BLOCKED" in out2))
    failed = [n for n, passed in checks if not passed]
    for n, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
