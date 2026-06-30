#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/"scripts/download_media_assets.py").read_text()+(ROOT/"scripts/fetch_source_posts.py").read_text()
ok="confirm-download" in src or "confirm_download" in src
print(f"  {'PASS' if ok else 'FAIL'} download confirm gate"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
