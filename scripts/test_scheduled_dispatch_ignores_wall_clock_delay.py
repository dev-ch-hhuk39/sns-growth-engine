#!/usr/bin/env python3
"""Scheduled event identity, not delayed runner wall time, owns a slot."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    "autonomous-growth-loop-night-scout.yml",
    "autonomous-growth-loop-liver-manager.yml",
    "direct-reference-media-night-scout.yml",
    "direct-reference-media-liver-manager.yml",
    "media-growth-post-night-scout.yml",
    "media-growth-post-liver-manager.yml",
]

checks = []
for name in WORKFLOWS:
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    checks.append((
        name,
        "Diagnose schedule delay" in text
        and "steps.schedule_window.outputs.in_window" not in text
        and "github.event_name == 'schedule'" in text,
    ))
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
