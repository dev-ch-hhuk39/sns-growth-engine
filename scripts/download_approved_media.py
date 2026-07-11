#!/usr/bin/env python3
"""Plan/download approved individual video URLs only."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import build_rights_decision
from discover_approved_source_videos import load_existing_source_videos



def is_individual_video_url(url: str) -> bool:
    parts = urlsplit(str(url or ""))
    host = parts.netloc.lower()
    path = parts.path
    if "tiktok.com" in host:
        return "/video/" in path
    if "youtube.com" in host:
        return path == "/watch" and bool(parts.query)
    if "youtu.be" in host:
        return len(path.strip("/")) > 0
    return False


def _resolve_source_video(args: argparse.Namespace) -> dict:
    injected = getattr(args, "source_video_row", None)
    if isinstance(injected, dict):
        return dict(injected)
    if not getattr(args, "source_video_id", ""):
        return {}
    for row in load_existing_source_videos(getattr(args, "source_videos_json", "")):
        if str(row.get("source_video_id", "")) == str(args.source_video_id):
            return dict(row)
    return {}


def build_download_plan(args: argparse.Namespace) -> dict:
    source_video = _resolve_source_video(args)
    source_url = source_video.get("canonical_video_url") or args.source_url
    rights_status = source_video.get("rights_status") or args.rights_status
    decision = build_rights_decision(rights_status, action="download")
    allow_env = os.environ.get("ALLOW_VIDEO_DOWNLOAD", "").lower() == "true"
    blocked = []
    if getattr(args, "source_video_id", "") and not source_video:
        blocked.append("source_video_id_not_found")
    if not decision.allowed:
        blocked.append(decision.reason)
    if not is_individual_video_url(source_url):
        blocked.append("individual_video_url_required")
    if str(source_video.get("download_status", "")).upper() == "DOWNLOADED":
        local_path = str(source_video.get("local_path", ""))
        if local_path and Path(local_path).exists():
            blocked.append("already_downloaded")
    if args.download and not args.confirm_download:
        blocked.append("--download requires --confirm-download")
    if args.download and not allow_env:
        blocked.append("ALLOW_VIDEO_DOWNLOAD=true is required")
    return {
        "status": "READY" if args.download and not blocked else "BLOCKED" if blocked else "PLAN_ONLY",
        "source_video_id": getattr(args, "source_video_id", ""),
        "source_url": source_url,
        "rights_status": decision.rights_status,
        "rights_decision": decision.as_dict(),
        "adapter_status": {"yt_dlp": "installed" if importlib.util.find_spec("yt_dlp") else "not_installed"},
        "output_dir": str(ROOT / "output" / "downloads"),
        "download": bool(args.download),
        "confirm_download": bool(args.confirm_download),
        "allow_video_download": allow_env,
        "would_download": bool(args.download and not blocked),
        "blocked_reasons": blocked,
        "download_result": {
            "media_asset_id": "",
            "local_path": "",
            "status": "NOT_DOWNLOADED",
        },
    }


def execute_download(plan: dict) -> dict:
    """Download one approved individual video. Secrets/cookies are never accepted or logged."""
    if plan.get("status") != "READY" or not plan.get("would_download"):
        return {**plan, "download_result": {"status": "NOT_DOWNLOADED", "media_asset_id": "", "local_path": ""}}
    if importlib.util.find_spec("yt_dlp") is None:
        return {**plan, "status": "FAILED", "blocked_reasons": ["yt_dlp_not_installed"]}
    import yt_dlp  # type: ignore[import]

    source_video_id = str(plan.get("source_video_id") or "video")
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_video_id)[:120]
    output_dir = Path(str(plan["output_dir"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / f"{safe_id}.%(ext)s")
    opts = {
        "outtmpl": template,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([str(plan["source_url"])])
        matches = sorted(output_dir.glob(f"{safe_id}.*"))
        local = next((p for p in matches if p.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}), None)
        if local is None:
            raise RuntimeError("download_output_missing")
        return {
            **plan,
            "status": "DOWNLOADED",
            "would_download": False,
            "download_result": {
                "status": "DOWNLOADED",
                "media_asset_id": f"download_{safe_id}",
                "local_path": str(local),
                "file_size_bytes": local.stat().st_size,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            **plan,
            "status": "FAILED",
            "would_download": False,
            "blocked_reasons": [f"{type(exc).__name__}: download_failed"],
            "download_result": {"status": "FAILED", "media_asset_id": "", "local_path": ""},
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="download approved media")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-video-id", default="")
    parser.add_argument("--source-videos-json", default="")
    parser.add_argument("--rights-status", default="third_party_reference_only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--confirm-download", action="store_true")
    args = parser.parse_args()
    if not args.source_url and not args.source_video_id:
        parser.error("--source-url or --source-video-id is required")
    plan = build_download_plan(args)
    if args.download and not args.dry_run and plan["status"] == "READY":
        plan = execute_download(plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["status"] in {"BLOCKED", "FAILED"} and args.download else 0


if __name__ == "__main__":
    raise SystemExit(main())
