#!/usr/bin/env python3
"""Scheduled slots safely stop rather than reuse a fixed fallback."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runner = (ROOT / "scripts/run_autonomous_loop.py").read_text(encoding="utf-8")
night = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8")
liver = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")

checks = [
    ("AUTO_READY exhaustion is visible", "AUTO_READY_REJECTED_ALL" in runner),
    ("safe no candidate is emitted", "SAFE_NO_CANDIDATE" in runner),
    ("production runner does not invoke fixed slot fallback", "--confirm-slot-fallback" not in runner),
    ("night manual dispatch chooses canonical slot", "MANUAL_SLOT_ID" in night and "ns_1600_original" in night),
    ("liver manual dispatch chooses canonical slot", "MANUAL_SLOT_ID" in liver and "lm_1000_original" in liver),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
