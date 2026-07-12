#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "scripts/run_media_growth_engine.py").read_text()

checks = [
    ("refresh helper tracks old ready state", "old_ready" in text),
    ("refresh helper tracks new ready state", "new_ready" in text),
    ("refreshes when candidate becomes ready", "new_ready and not old_ready" in text),
    ("preserves already posted clips", "post_status" in text and "POSTED" in text),
    ("preserves uploaded clips", "upload_status" in text and "UPLOADED" in text),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
