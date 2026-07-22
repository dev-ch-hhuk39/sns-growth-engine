#!/usr/bin/env python3
"""All production yt-dlp routes use the configured Node runtime helper."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from acquisition.ytdlp_runtime import YOUTUBE_EJS_COMPONENT, metadata_options
paths = [
    "src/acquisition/ytdlp.py",
    "src/acquisition/enrichment.py",
    "scripts/collect_video_references.py",
    "scripts/discover_approved_source_posts.py",
    "scripts/discover_approved_source_videos.py",
    "scripts/download_approved_media.py",
    "scripts/ingest_direct_reference_media.py",
    "scripts/transcribe_approved_source_videos.py",
    "src/video/video_downloader.py",
]
missing = []
for relative in paths:
    text = (ROOT / relative).read_text(encoding="utf-8")
    if "metadata_options" not in text:
        missing.append(relative)
assert not missing, missing
os.environ["SNS_YTDLP_NODE_PATH"] = "/opt/sns-approved-node"
youtube = metadata_options("youtube", {"skip_download": True})
tiktok = metadata_options("tiktok", {"skip_download": True})
assert youtube["js_runtimes"] == {"node": {"path": "/opt/sns-approved-node"}}
assert youtube["remote_components"] == [YOUTUBE_EJS_COMPONENT]
assert "remote_components" not in tiktok
print(f"PASS test_ytdlp_node_runtime_configured.py ({len(paths)} routes)")
