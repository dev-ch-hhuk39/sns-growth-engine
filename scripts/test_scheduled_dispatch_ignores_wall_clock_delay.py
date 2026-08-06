#!/usr/bin/env python3
"""Delayed scheduled events preserve work but must not publish outside the window."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_WORKFLOWS = [
    "autonomous-growth-loop-night-scout.yml",
    "autonomous-growth-loop-liver-manager.yml",
]
MEDIA_WORKFLOWS = [
    "direct-reference-media-night-scout.yml",
    "direct-reference-media-liver-manager.yml",
    "media-growth-post-night-scout.yml",
    "media-growth-post-liver-manager.yml",
]

checks = []
for name in TEXT_WORKFLOWS:
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    checks.append((
        name,
        "Early runtime preflight" in text
        and "scheduled_window_decision" in text
        and "run_scheduled_text_slot_pipeline.py" in text,
    ))
for name in MEDIA_WORKFLOWS:
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    checks.append((
        name,
        "Early runtime preflight" in text
        and "scheduled_window_decision" in text
        and "Stop delayed scheduled execution" in text
        and "candidate" in text.lower()
        and "exit 2" in text,
    ))
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
