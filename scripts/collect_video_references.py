#!/usr/bin/env python3
"""Collect video reference metadata without downloading media."""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any

PUBLIC_TIMEOUT_SECONDS = 15


def adapter_status() -> dict[str, str]:
    return {
        "yt_dlp": "installed" if importlib.util.find_spec("yt_dlp") else "not_installed",
        "youtube_transcript_api": "installed" if importlib.util.find_spec("youtube_transcript_api") else "not_installed",
        "public_og": "wired",
        "download": "blocked",
    }


def _meta(pattern: str, text: str) -> str:
    m = re.search(pattern, text, flags=re.I | re.S)
    return html.unescape(m.group(1).strip()) if m else ""


def fetch_video_metadata(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sns-growth-engine/2.0; +dry-run)"})
    try:
        with urllib.request.urlopen(req, timeout=PUBLIC_TIMEOUT_SECONDS) as res:
            body = res.read(2_000_000).decode("utf-8", errors="replace")
        return {
            "ok": True,
            "title": _meta(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)', body),
            "thumbnail_url": _meta(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']*)', body),
            "author_handle": _meta(r'"ownerChannelName"\s*:\s*"([^"]+)"', body),
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "title": "", "thumbnail_url": "", "author_handle": "", "error": f"{type(exc).__name__}: {exc}"}


def fetch_ytdlp_metadata(url: str) -> dict[str, Any]:
    try:
        import yt_dlp
    except Exception as exc:
        return {"ok": False, "title": "", "thumbnail_url": "", "author_handle": "", "extractor": "", "error": f"yt_dlp_not_installed: {type(exc).__name__}"}
    try:
        class QuietLogger:
            def debug(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg): pass

        opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietLogger(),
            "noplaylist": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "ok": True,
            "title": info.get("title", ""),
            "thumbnail_url": info.get("thumbnail", ""),
            "author_handle": info.get("uploader") or info.get("channel") or "",
            "duration": info.get("duration", ""),
            "extractor": info.get("extractor_key", ""),
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "title": "", "thumbnail_url": "", "author_handle": "", "extractor": "", "error": f"yt_dlp_error: {type(exc).__name__}"}


def fetch_youtube_transcript(url: str) -> dict[str, Any]:
    video_id = ""
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{6,})", url)
    if m:
        video_id = m.group(1)
    if not video_id:
        return {"status": "UNAVAILABLE", "reason": "youtube_video_id_missing", "text": ""}
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": f"youtube_transcript_api_not_installed: {type(exc).__name__}", "text": ""}
    try:
        chunks = YouTubeTranscriptApi.get_transcript(video_id, languages=["ja", "en"])
        text = "\n".join(str(c.get("text", "")) for c in chunks if c.get("text"))
        return {"status": "FETCHED", "reason": "", "text": text[:5000], "chunk_count": len(chunks)}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": f"transcript_unavailable: {type(exc).__name__}", "text": ""}


def build_video_reference(url: str, account_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    platform = "youtube" if "youtu" in url else "tiktok" if "tiktok" in url else "video"
    metadata = metadata or {}
    return {
        "reference_post_id": f"video_ref_{account_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "account_id": account_id,
        "platform": platform,
        "video_url": url,
        "title": metadata.get("title", ""),
        "author_handle": metadata.get("author_handle", ""),
        "thumbnail_url": metadata.get("thumbnail_url", ""),
        "extractor": metadata.get("extractor", ""),
        "duration": metadata.get("duration", ""),
        "metadata_status": "FETCHED" if metadata.get("ok") else "PLAN_ONLY" if not metadata else "UNAVAILABLE",
        "fetch_error": metadata.get("error", ""),
        "rights_status": "third_party_reference_only",
        "can_download": False,
        "can_cut": False,
        "can_upload": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="collect video references safely")
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--fetch-metadata", action="store_true")
    parser.add_argument("--metadata-adapter", default="auto", choices=["auto", "public", "yt-dlp"])
    parser.add_argument("--fetch-transcript", action="store_true")
    parser.add_argument("--account-id", default="night_scout", choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-collect", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account disabled"}, ensure_ascii=False))
        return 1
    rows = []
    transcripts = []
    for url in (args.url or ["reference_only://sample"]):
        meta = {}
        if args.fetch_metadata and url.startswith("http"):
            if args.metadata_adapter in {"auto", "yt-dlp"}:
                meta = fetch_ytdlp_metadata(url)
            if (not meta.get("ok")) and args.metadata_adapter in {"auto", "public"}:
                meta = fetch_video_metadata(url)
        rows.append(build_video_reference(url, args.account_id, meta))
        if args.fetch_transcript:
            transcripts.append({"video_url": url, **fetch_youtube_transcript(url)})
    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", "adapter_status": adapter_status(), "download": False, "rows": rows, "transcripts": transcripts}, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_collect or not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-collect --use-sheets"}, ensure_ascii=False))
        return 1
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    ws = client._ws("reference_posts")
    headers = ws.row_values(1)
    ws.append_rows([[str(row.get(h, "")) for h in headers] for row in rows], value_input_option="USER_ENTERED")
    print(json.dumps({"status": "APPLIED", "reference_posts_appended": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
