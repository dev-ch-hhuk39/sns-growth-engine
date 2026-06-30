#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v", ROOT / "scripts/collect_video_references.py")
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
row = v.build_video_reference("https://www.tiktok.com/@example/video/123", "night_scout", {})
checks = [
    ("platform tiktok", row["platform"] == "tiktok"),
    ("download false", row["can_download"] is False),
    ("cut false", row["can_cut"] is False),
    ("upload false", row["can_upload"] is False),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
