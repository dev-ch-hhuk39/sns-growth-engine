#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "docs/production-pilot-runbook.md"
text = path.read_text(encoding="utf-8") if path.exists() else ""
required = [
    "Purpose",
    "Current Pilot Candidates",
    "Pilot Apply Procedure",
    "Rollback",
    "AUTOPOST",
    "fetch_enabled",
]
checks = [("exists", path.exists())] + [(f"mentions {item}", item in text) for item in required]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
