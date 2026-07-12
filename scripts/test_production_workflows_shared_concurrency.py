#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = [
    ".github/workflows/autonomous-growth-loop-night-scout.yml",
    ".github/workflows/autonomous-growth-loop-liver-manager.yml",
    ".github/workflows/production-autopilot-aftercare.yml",
    ".github/workflows/media-transcription-production.yml",
    ".github/workflows/media-growth-production.yml",
]
checks = []
for rel in files:
    text = (ROOT / rel).read_text(encoding="utf-8")
    checks.append((f"{rel} shared concurrency", "group: sns-growth-production-${{ github.ref }}" in text))
    checks.append((f"{rel} no cancel", "cancel-in-progress: false" in text))
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
