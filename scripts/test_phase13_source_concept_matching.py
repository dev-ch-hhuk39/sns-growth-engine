#!/usr/bin/env python3
"""Verify concept/subject policies are present for production sources."""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    with open(os.path.join(_ROOT, "config/source_accounts/production_sources.example.json"), encoding="utf-8") as f:
        sources = json.load(f)["sources"]
    night_video = [s for s in sources if "night_scout" in s.get("target_account_ids", []) and s.get("source_platform") == "youtube"]
    beauty = [s for s in sources if "beauty_account" in s.get("target_account_ids", []) and s.get("source_platform") != "query"]
    checks = [
        ("night videos require female subject", all(s.get("subject_policy", {}).get("female_subject_required") for s in night_video)),
        ("night videos block aggressive recruiting", all(s.get("subject_policy", {}).get("no_aggressive_recruiting") for s in night_video)),
        ("beauty medical review required", all(s.get("subject_policy", {}).get("beauty_medical_risk_review_required") for s in beauty)),
        ("require transform", all(s.get("subject_policy", {}).get("require_transform") for s in sources)),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
