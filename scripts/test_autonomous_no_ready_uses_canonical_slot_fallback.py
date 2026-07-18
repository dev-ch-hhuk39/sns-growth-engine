#!/usr/bin/env python3
"""Scheduled text slots retain a bounded safe fallback when AUTO_READY is empty."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runner = (ROOT / "scripts/run_autonomous_loop.py").read_text(encoding="utf-8")
night = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8")
liver = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")

checks = [
    ("no AUTO_READY result invokes named fallback", "auto_ready_rejected_all" in runner),
    ("fallback still requires canonical text slot", "slot.get(\"post_type\") in TEXT_POST_TYPES" in runner),
    ("fallback requires its explicit confirmation", "--confirm-slot-fallback" in runner),
    ("queue worker is skipped after fallback post", "canonical_slot_fallback_already_posted" in runner),
    ("night manual dispatch chooses canonical slot", "MANUAL_SLOT_ID" in night and "ns_1600_original" in night),
    ("liver manual dispatch chooses canonical slot", "MANUAL_SLOT_ID" in liver and "lm_1000_original" in liver),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
