#!/usr/bin/env python3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cut_approved_clips as cutter
import download_approved_media as downloader
import upload_media_assets as uploader


class FakeYDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def download(self, _urls):
        Path(self.options["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(b"video")


class FakeYtDlp:
    YoutubeDL = FakeYDL


class FakeCloudinaryUploader:
    @staticmethod
    def upload(_path, **_kwargs):
        return {"secure_url": "https://res.cloudinary.com/example/video/upload/test.mp4", "public_id": "test"}


class FakeCloudinary:
    uploader = FakeCloudinaryUploader

    @staticmethod
    def config(**_kwargs):
        return None


checks = []
with TemporaryDirectory() as tmp:
    download_plan = {
        "status": "READY",
        "would_download": True,
        "source_video_id": "sv_test",
        "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "output_dir": tmp,
        "blocked_reasons": [],
    }
    with patch.object(downloader.importlib.util, "find_spec", return_value=True), patch.dict(sys.modules, {"yt_dlp": FakeYtDlp()}):
        downloaded = downloader.execute_download(download_plan)
    checks.append(downloaded["status"] == "DOWNLOADED" and Path(downloaded["download_result"]["local_path"]).exists())

    cut_output = Path(tmp) / "clip.mp4"

    def fake_run(cmd, **_kwargs):
        Path(cmd[-1]).write_bytes(b"clip")
        return SimpleNamespace(returncode=0, stderr="")

    cut_plan = {
        "status": "READY",
        "would_cut": True,
        "input_path": downloaded["download_result"]["local_path"],
        "output_path": str(cut_output),
        "start_seconds": 0,
        "duration_seconds": 12,
        "vertical_9x16": True,
        "clip_candidate_id": "clip_test",
        "media_asset_result": {"rights_status": "approved_creator_clip"},
    }
    with patch.object(cutter.subprocess, "run", side_effect=fake_run):
        cut = cutter.execute_cut(cut_plan)
    checks.append(cut["status"] == "CUT" and cut["media_asset_result"]["aspect_ratio"] == "9:16")

    asset = {**cut["media_asset_result"], "account_id": "liver_manager", "status": "APPROVED", "rights_status": "approved_creator_clip"}
    args = SimpleNamespace(upload=True, confirm_upload=True, dry_run=False)
    with patch.dict(sys.modules, {"cloudinary": FakeCloudinary, "cloudinary.uploader": FakeCloudinaryUploader}), patch.object(uploader.importlib.util, "find_spec", return_value=True), patch.dict(uploader.os.environ, {
        "ALLOW_CLOUDINARY_UPLOAD": "true",
        "CLOUDINARY_CLOUD_NAME": "present",
        "CLOUDINARY_API_KEY": "present",
        "CLOUDINARY_API_SECRET": "present",
    }, clear=False):
        uploaded = uploader.execute_cloudinary_uploads(uploader.build_upload_plan(args, [asset]))
    checks.append(uploaded["status"] == "UPLOADED" and uploaded["uploaded_count"] == 1)

print(f"PASS: {sum(checks)} / FAIL: {len(checks)-sum(checks)}")
raise SystemExit(0 if all(checks) else 1)
