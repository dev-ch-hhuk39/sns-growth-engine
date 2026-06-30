#!/usr/bin/env python3
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
doc = (ROOT / "docs/dependency-inventory.md").read_text(encoding="utf-8")
installed = shutil.which("cli-anything") is not None
checks = [
    ("cli-anything documented", "CLI-Anything Clarification" in doc),
    ("not in requirements", "cli-anything" not in (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()),
    ("not claimed installed unless binary", installed or "CLI-Anything | external signals | optional / not_found" in doc),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
