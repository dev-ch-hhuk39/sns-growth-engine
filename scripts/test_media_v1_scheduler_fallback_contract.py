#!/usr/bin/env python3
"""Media fallback remains observable text fallback, never media success."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "scripts" / "reconcile_due_production_slots.py").read_text(encoding="utf-8")

checks = {
    "media candidates sort before text": "not has_media(row) if media_slot else False" in text,
    "fallback reason is explicit": '"NO_HARD_GATE_MEDIA" if media_fallback' in text,
    "expected type is retained": '"expected_type": slot["post_type"]' in text,
    "fallback actual type is text": '"actual_type": "text_fallback" if media_fallback' in text,
    "fallback is not media success": 'actual_post_type="text_fallback" if media_fallback' in text,
}
for name, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks.items() if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
