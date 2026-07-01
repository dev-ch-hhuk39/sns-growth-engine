#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
violations = []
for s in sources:
    targets = s.get("target_account_ids") or [s.get("target_account_id") or s.get("account_id")]
    if "beauty_account" in targets and (s.get("active") is True or str(s.get("active")).lower() == "true"):
        violations.append(s.get("source_id"))
checks = [("beauty inactive", not violations)]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
if violations:
    print("violations:", violations[:20])
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
