#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
files=[p for p in (ROOT/"scripts").glob("*cloudinary*.py")]+[ROOT/"scripts/upload_media_assets.py"]
src="".join(p.read_text() for p in files if p.exists())
ok=("confirm-upload" in src or "confirm_upload" in src) and "ALLOW_CLOUDINARY_UPLOAD" in src
print(f"  {'PASS' if ok else 'FAIL'} cloudinary confirm gate"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
