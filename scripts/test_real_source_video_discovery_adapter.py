#!/usr/bin/env python3
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import discover_approved_source_videos as discovery


class FakeYDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_info(self, _url, download=False):
        assert download is False
        assert self.options["playlistend"] <= 50
        return {"entries": [{"id": "abcdefghijk", "title": "公開動画", "duration": 65}]}


class FakeModule:
    YoutubeDL = FakeYDL


source = {
    "source_id": "src_lm_yt_user_001",
    "source_platform": "youtube",
    "source_type": "channel",
    "source_url": "https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ",
    "target_account_id": "liver_manager",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
config = {"max_videos_per_source_scan": 50, "max_new_videos_per_source_per_run": 10}

with patch.object(discovery.importlib.util, "find_spec", return_value=True), patch.dict(sys.modules, {"yt_dlp": FakeModule()}):
    rows, status = discovery.discover_source_videos_real(source, config)

checks = [
    status == "REAL_DISCOVERY",
    len(rows) == 1,
    rows[0]["video_id"] == "abcdefghijk",
    rows[0]["canonical_video_url"] == "https://www.youtube.com/watch?v=abcdefghijk",
    rows[0]["duration_seconds"] == 65,
]
print(f"PASS: {sum(checks)} / FAIL: {len(checks)-sum(checks)}")
raise SystemExit(0 if all(checks) else 1)
