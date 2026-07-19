#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.factory import build_provider_registry

registry = build_provider_registry()
required = {"youtube_transcript_api", "youtube_comment_downloader", "threads_public_comments", "yt_dlp_post_detail", "firecrawl_optional"}
checks = [
    ("non-profile providers are registered", required.issubset(registry)),
    ("transcript provider exposes contract method", hasattr(registry["youtube_transcript_api"], "fetch_transcript")),
    ("comment providers expose contract method", all(hasattr(registry[name], "fetch_comments") for name in ("youtube_comment_downloader", "threads_public_comments"))),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
