#!/usr/bin/env python3
"""Test source-to-post production path remains dry-run and blocked for publish."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.orchestrators.source_to_post_orchestrator import run_pipeline


def main() -> int:
    result = run_pipeline(account_id="night_scout", platform="threads", source_platform="youtube", mock=True, dry_run=True)
    checks = [
        ("status BLOCKED without confirm-post", result["status"] == "BLOCKED"),
        ("media step exists", "media_plan" in result["steps"]),
        ("publish plan blocked", result["steps"]["publish_plan"]["status"] == "BLOCKED"),
        ("no real post", result["safety"]["no_real_post"] and not result["safety"]["real_post"]),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
