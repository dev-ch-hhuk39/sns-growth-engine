#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
approved = {"owned", "licensed", "approved_creator_clip"}
violations = []
for s in sources:
    if str(s.get("clip_enabled", "")).lower() == "true" or s.get("clip_enabled") is True:
        rights = str(s.get("rights_status") or s.get("rights_policy") or "").lower()
        if rights not in approved:
            violations.append((s.get("source_id"), rights))
checks = [("clip enabled only approved", not violations)]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
if violations:
    print("violations:", violations[:20])
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
