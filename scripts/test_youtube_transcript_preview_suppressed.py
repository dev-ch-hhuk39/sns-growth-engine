#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
collect = (ROOT / "scripts/collect_video_references.py").read_text(encoding="utf-8")
transcribe = (ROOT / "scripts/transcribe_video_reference.py").read_text(encoding="utf-8")
docs = (ROOT / "docs/dependency-inventory.md").read_text(encoding="utf-8").lower()
checks = [
    ("collect text empty", '"text": ""' in collect),
    ("transcribe preview empty", '"text_preview": ""' in transcribe),
    ("docs mention preview suppressed", "preview is suppressed" in docs or "transcript text preview is suppressed" in docs),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
