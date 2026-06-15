#!/usr/bin/env python3
"""Verify trend query sources exist and remain fetch-gated."""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    with open(os.path.join(_ROOT, "config/source_accounts/production_sources.example.json"), encoding="utf-8") as f:
        sources = json.load(f)["sources"]
    queries = [s for s in sources if s.get("source_category") == "trend_query" and s.get("source_platform") == "query"]
    by_account = {
        acc: len([s for s in queries if acc in s.get("target_account_ids", [])])
        for acc in ("night_scout", "liver_manager", "beauty_account")
    }
    checks = [
        ("night_scout query 13", by_account["night_scout"] == 13),
        ("liver_manager query 11", by_account["liver_manager"] == 11),
        ("beauty_account query 13", by_account["beauty_account"] == 13),
        ("all fetch disabled", all(not s.get("fetch_enabled") and not s.get("active") for s in queries)),
        ("pdca/original_hypothesis connected", all("pdca_source" in s.get("use_cases", []) and "original_hypothesis" in s.get("use_cases", []) for s in queries)),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
