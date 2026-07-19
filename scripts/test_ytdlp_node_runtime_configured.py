#!/usr/bin/env python3
"""All production yt-dlp routes explicitly use the hosted runner's Node."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
    if '"js_runtimes": {"node": {}}' not in text:
        missing.append(relative)
assert not missing, missing
print(f"PASS test_ytdlp_node_runtime_configured.py ({len(paths)} routes)")
