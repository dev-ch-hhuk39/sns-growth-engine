#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
collect = (ROOT / "scripts/collect_video_references.py").read_text(encoding="utf-8")
docs = (ROOT / "docs/dependency-inventory.md").read_text(encoding="utf-8").lower()
checks = [
    ("extract_info no download", "extract_info(url, download=False)" in collect),
    ("skip download option", '"skip_download": True' in collect),
    ("policy says download false", "download=false" in docs),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
