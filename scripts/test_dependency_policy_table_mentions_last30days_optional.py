#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "docs/dependency-inventory.md").read_text(encoding="utf-8").lower()
checks = [
    ("last30days mentioned", "last30days" in text),
    ("last30days optional", "last30days" in text and "optional" in text),
    ("trend signal", "trend signal" in text or "trend/source discovery" in text),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
