#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
violations = [
    s.get("source_id")
    for s in sources
    if str(s.get("source_platform") or s.get("platform") or "").lower() == "x"
    and (s.get("fetch_enabled") is True or str(s.get("fetch_enabled")).lower() == "true")
    and not (s.get("source_id") == "src_lm_x_cand_001" and s.get("x_read_only") is True and s.get("target_account_ids") == ["liver_manager"])
]
checks = [("unapproved x fetch disabled", not violations)]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
if violations:
    print("violations:", violations[:20])
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
