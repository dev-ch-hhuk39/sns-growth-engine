#!/usr/bin/env python3
"""A delayed GitHub schedule must skip publishing instead of posting late."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_schedule_window import build_result  # noqa: E402


CASES = [
    ("opens at the 15-minute early boundary", "ns_1800_direct_media", "2026-07-18T08:45:00Z", True),
    ("opens at the target time", "lm_1800_clip_media", "2026-07-18T09:00:00Z", True),
    ("blocks a delayed schedule", "ns_1800_direct_media", "2026-07-18T10:04:00Z", False),
    ("handles the 25:00 business slot", "ns_2500_pdca", "2026-07-18T15:45:00Z", True),
]


def main() -> int:
    failures = 0
    for label, slot_id, now_utc, expected in CASES:
        result = build_result(slot_id, now_utc, 15)
        ok = result["in_window"] is expected
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'} {label}: {result['status']}")
    print(f"PASS: {len(CASES) - failures} / FAIL: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
