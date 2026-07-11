#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
download = (ROOT / "scripts/download_approved_media.py").read_text()
cut = (ROOT / "scripts/cut_approved_clips.py").read_text()
upload = (ROOT / "scripts/upload_media_assets.py").read_text()
runner = (ROOT / "scripts/run_media_production_pipeline.py").read_text()

checks = [
    "ydl.download" in download and "execute_download" in download,
    "subprocess.run" in cut and "execute_cut" in cut,
    "cloudinary.uploader.upload" in upload and "execute_cloudinary_uploads" in upload,
    "process_one(client" in runner,
    "validate_media_post" in runner,
    "media_daily_post_cap" in runner,
    "third_party_reference_only" not in runner.split("APPROVED_RIGHTS", 1)[0],
]
print(f"PASS: {sum(checks)} / FAIL: {len(checks)-sum(checks)}")
raise SystemExit(0 if all(checks) else 1)
