#!/usr/bin/env python3
"""Verify PDCA suggestions are review-only and do not auto-apply source priority."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.orchestrators.source_to_post_orchestrator import run_pipeline


def main() -> int:
    result = run_pipeline(account_id="night_scout", platform="x", source_platform="x", mock=True, dry_run=True)
    suggestions = result["steps"]["pdca_candidates"]["next_collection_candidates"]
    checks = [
        ("pdca suggestions exist", bool(suggestions)),
        ("waiting review", all(s.get("status") == "WAITING_REVIEW" for s in suggestions)),
        ("auto_apply false", all(s.get("auto_apply") is False for s in suggestions)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
