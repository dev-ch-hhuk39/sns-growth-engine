#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = {
    ".github/workflows/autonomous-growth-loop-night-scout.yml": "night-scout",
    ".github/workflows/direct-reference-media-night-scout.yml": "night-scout",
    ".github/workflows/media-growth-post-night-scout.yml": "night-scout",
    ".github/workflows/media-growth-production-night-scout.yml": "night-scout",
    ".github/workflows/autonomous-growth-loop-liver-manager.yml": "liver-manager",
    ".github/workflows/direct-reference-media-liver-manager.yml": "liver-manager",
    ".github/workflows/media-growth-post-liver-manager.yml": "liver-manager",
    ".github/workflows/media-growth-production.yml": "liver-manager",
    ".github/workflows/media-transcription-production.yml": "liver-manager",
}
checks = []
for rel, account_slug in files.items():
    text = (ROOT / rel).read_text(encoding="utf-8")
    expected = f"group: sns-growth-production-{account_slug}-${{{{ github.ref }}}}"
    checks.append((f"{rel} account scoped concurrency", expected in text))
    checks.append((f"{rel} no cancel", "cancel-in-progress: false" in text))
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
