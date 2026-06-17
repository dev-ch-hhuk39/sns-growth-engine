#!/usr/bin/env python3
"""Verify generation jobs remain draft/review only in production path."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.orchestrators.source_to_post_orchestrator import run_pipeline


def main() -> int:
    normal = run_pipeline(account_id="night_scout", platform="x", source_platform="x", mock=True, dry_run=True)
    beauty = run_pipeline(account_id="beauty_account", platform="threads", source_platform="youtube", mock=True, dry_run=True)
    checks = [
        ("normal drafts are DRAFT", all(d["status"] == "DRAFT" for d in normal["steps"]["generation"]["drafts"])),
        ("beauty waiting review", all(d["status"] == "WAITING_REVIEW" for d in beauty["steps"]["generation"]["drafts"])),
        ("beauty not posted", beauty["status"] in {"BLOCKED", "WAITING_REVIEW"}),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
