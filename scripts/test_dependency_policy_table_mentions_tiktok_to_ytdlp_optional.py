#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "docs/dependency-inventory.md").read_text(encoding="utf-8").lower()
checks = [
    ("tiktok-to-ytdlp mentioned", "tiktok-to-ytdlp" in text),
    ("optional helper", "optional helper" in text or "optional / imported adapter" in text),
    ("video url preferred", "/video/" in text),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
