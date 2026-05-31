"""
youtube_video_collector.py - YouTube動画メタデータ収集アダプター

設計:
  - 実 YouTube Data API 呼び出しは ALLOW_YOUTUBE_COLLECTION=true の場合のみ行う（未実装）
  - mock / JSON ファイル入力で全テストが通る
  - 収集した動画は reference_posts タブに保存する（content_type=video）
  - yt-dlp によるダウンロードはしない（メタデータ収集のみ）

normalized_video_reference フォーマット（reference_posts 保存用）:
  id, account_id, platform, content_type, video_id, video_url,
  creator_handle, channel_id, channel_name, title, description,
  duration_seconds, thumbnail_url, likes, reposts, comment_count,
  impressions, published_at, raw_payload_json,
  transcription_status, clip_generation_status,
  collected_at, status, notes
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def normalize_youtube_video(raw: dict[str, Any], account_id: str) -> dict[str, Any]:
    """YouTube API レスポンス（またはmock dict）を normalized_video_reference に変換する。

    Args:
        raw: YouTube Data API の video resource 相当のdict
        account_id: 対象アカウント（night_scout / liver_manager）

    Returns:
        reference_posts タブに保存可能なdict
    """
    video_id = str(raw.get("video_id", raw.get("id", "")))
    snippet = raw.get("snippet", raw)
    statistics = raw.get("statistics", raw)
    content_details = raw.get("contentDetails", raw)

    channel_id = str(snippet.get("channelId", raw.get("channel_id", "")))
    channel_name = str(snippet.get("channelTitle", raw.get("channel_name", "")))
    creator_handle = str(raw.get("creator_handle", raw.get("handle", channel_name)))
    title = str(snippet.get("title", raw.get("title", "")))
    description = str(snippet.get("description", raw.get("description", "")))
    published_at = str(snippet.get("publishedAt", raw.get("published_at", "")))
    thumbnail_url = _extract_thumbnail(snippet.get("thumbnails", {}), raw.get("thumbnail_url", ""))

    likes = int(statistics.get("likeCount", raw.get("likes", 0)) or 0)
    comment_count = int(statistics.get("commentCount", raw.get("comment_count", 0)) or 0)
    view_count = int(statistics.get("viewCount", raw.get("impressions", 0)) or 0)
    duration_seconds = _parse_duration(
        content_details.get("duration", ""),
        raw.get("duration_seconds", 0),
    )

    video_url = raw.get("video_url", f"https://www.youtube.com/watch?v={video_id}")

    return {
        "id": raw.get("id", f"ref-yt-{_short_uuid()}"),
        "created_at": _now(),
        "account_id": account_id,
        "platform": "youtube",
        "content_type": "video",
        "video_id": video_id,
        "video_url": video_url,
        "post_url": video_url,
        "post_id": video_id,
        "creator_handle": creator_handle,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "title": title,
        "description": description[:500] if description else "",
        "text": title,
        "duration_seconds": duration_seconds,
        "thumbnail_url": thumbnail_url,
        "likes": likes,
        "reposts": 0,
        "impressions": view_count,
        "comment_count": comment_count,
        "published_at": published_at,
        "raw_payload_json": json.dumps(raw, ensure_ascii=False)[:2000],
        "transcription_status": "pending",
        "clip_generation_status": "pending",
        "collected_at": _now(),
        "status": "ACTIVE",
        "notes": "",
        "source_type": "youtube_channel",
        "author": channel_name,
        "media_urls": thumbnail_url,
    }


def _extract_thumbnail(thumbnails: dict, fallback: str) -> str:
    if not thumbnails:
        return fallback
    for quality in ("maxres", "high", "medium", "default"):
        t = thumbnails.get(quality, {})
        if isinstance(t, dict) and t.get("url"):
            return str(t["url"])
    return fallback


def _parse_duration(iso_duration: str, fallback: int) -> int:
    """ISO8601 duration (PT4M30S) を秒数に変換する。"""
    if not iso_duration or not iso_duration.startswith("PT"):
        return int(fallback or 0)
    try:
        s = iso_duration[2:]
        minutes = 0
        seconds = 0
        if "M" in s:
            parts = s.split("M")
            minutes = int(parts[0])
            s = parts[1]
        if "S" in s:
            seconds = int(s.replace("S", ""))
        return minutes * 60 + seconds
    except Exception:
        return int(fallback or 0)


def collect_from_mock(
    mock_videos: list[dict[str, Any]],
    account_id: str,
) -> list[dict[str, Any]]:
    """モックデータ（dicts のリスト）から normalized_video_reference を生成する。"""
    return [
        normalize_youtube_video(v, account_id)
        for v in mock_videos
        if str(v.get("content_type", "video")).lower() == "video"
        and v.get("platform", "youtube").lower() in ("youtube", "")
    ]


def collect_from_json_file(
    json_path: str,
    account_id: str,
) -> list[dict[str, Any]]:
    """JSON ファイルからモックデータを読み込んで正規化する。"""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        videos = [v for v in data if v.get("platform", "").lower() == "youtube"]
    elif isinstance(data, dict):
        videos = data.get("youtube", data.get("videos", []))
    else:
        videos = []
    return collect_from_mock(videos, account_id)


def save_video_references(
    client: Any,
    references: list[dict[str, Any]],
    *,
    dry_run: bool = True,
) -> dict[str, int]:
    """normalized_video_reference を reference_posts タブに保存する。"""
    if dry_run:
        print(f"[dry-run] save_video_references: {len(references)} 件（書き込みスキップ）")
        for ref in references:
            print(f"  video_id={ref.get('video_id', '?')!r} title={str(ref.get('title', ''))[:40]!r}")
        return {"added": 0, "skipped": len(references), "errors": 0}
    return client.save_reference_posts(references)
