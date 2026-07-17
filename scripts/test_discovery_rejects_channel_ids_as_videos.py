#!/usr/bin/env python3
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import discover_approved_source_videos as discovery  # noqa: E402

source = inspect.getsource(discovery.discover_source_videos_real)
checks = [
    ("youtube discovery requires 11 character video id", 'platform == "youtube" and len(video_id) != 11' in source),
    ("tiktok discovery requires numeric video id", 'platform == "tiktok" and not video_id.isdigit()' in source),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
