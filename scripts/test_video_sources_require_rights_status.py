#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
video_sources = [s for s in sources if str(s.get("source_platform") or s.get("platform") or "").lower() in {"youtube", "tiktok"}]
missing = [s.get("source_id") for s in video_sources if not (s.get("rights_status") or s.get("rights_policy"))]
checks = [("video sources present", bool(video_sources)), ("rights present", not missing)]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
if missing:
    print("missing:", missing[:20])
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
