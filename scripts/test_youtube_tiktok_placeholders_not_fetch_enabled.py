#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
todos = [s for s in sources if str(s.get("source_id", "")).endswith("_todo") or s.get("current_status") == "needs_human_url"]
checks = [
    ("todo count", len(todos) >= 4),
    ("todo fetch false", all(s.get("fetch_enabled") is False for s in todos)),
    ("todo manual only", all(s.get("manual_only") is True for s in todos)),
    ("todo unknown rights", all(str(s.get("rights_status", "")).lower() == "unknown" for s in todos)),
    ("todo empty urls", all(not str(s.get("source_url", "")).strip() for s in todos)),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
