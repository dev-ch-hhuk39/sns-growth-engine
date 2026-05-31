"""
tiktok_video_collector.py - TikTok動画メタデータ収集アダプター

設計:
  - 実 TikTok API 呼び出しは行わない（TikTok公式APIは厳格な審査が必要）
  - mock / JSON ファイル入力で全テストが通る
  - 将来的には非公式ライブラリ（TikTok-Api等）か手動入力を想定
  - 収集した動画は reference_posts タブに保存する（content_type=video）

normalized_video_reference フォーマット（reference_posts 保存用）は
youtube_video_collector と共通。
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


def normalize_tiktok_video(raw: dict[str, Any], account_id: str) -> dict[str, Any]:
    """TikTok動画データ（またはmock dict）を normalized_video_reference に変換する。

    Args:
        raw: TikTok動画情報を含むdict（video_id / creator_handle / title / likes 等）
        account_id: 対象アカウント（night_scout / liver_manager）

    Returns:
        reference_posts タブに保存可能なdict
    """
    video_id = str(raw.get("video_id", raw.get("id", _short_uuid())))
    creator_handle = str(raw.get("creator_handle", raw.get("author", raw.get("handle", ""))))
    channel_id = str(raw.get("channel_id", raw.get("user_id", creator_handle)))
    channel_name = str(raw.get("channel_name", raw.get("author_name", creator_handle)))
    title = str(raw.get("title", raw.get("desc", "")))
    description = str(raw.get("description", raw.get("desc", "")))
    duration_seconds = int(raw.get("duration_seconds", raw.get("duration", 0)) or 0)
    likes = int(raw.get("likes", raw.get("diggCount", 0)) or 0)
    comment_count = int(raw.get("comment_count", raw.get("commentCount", 0)) or 0)
    view_count = int(raw.get("impressions", raw.get("playCount", 0)) or 0)
    reposts = int(raw.get("reposts", raw.get("shareCount", 0)) or 0)
    published_at = str(raw.get("published_at", raw.get("createTime", "")))
    thumbnail_url = str(raw.get("thumbnail_url", raw.get("cover", "")))
    video_url = raw.get("video_url", f"https://www.tiktok.com/@{creator_handle}/video/{video_id}")

    return {
        "id": raw.get("id", f"ref-tk-{_short_uuid()}"),
        "created_at": _now(),
        "account_id": account_id,
        "platform": "tiktok",
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
        "text": title or description,
        "duration_seconds": duration_seconds,
        "thumbnail_url": thumbnail_url,
        "likes": likes,
        "reposts": reposts,
        "impressions": view_count,
        "comment_count": comment_count,
        "published_at": published_at,
        "raw_payload_json": json.dumps(raw, ensure_ascii=False)[:2000],
        "transcription_status": "pending",
        "clip_generation_status": "pending",
        "collected_at": _now(),
        "status": "ACTIVE",
        "notes": "",
        "source_type": "tiktok_account",
        "author": channel_name or creator_handle,
        "media_urls": thumbnail_url,
    }


def collect_from_mock(
    mock_videos: list[dict[str, Any]],
    account_id: str,
) -> list[dict[str, Any]]:
    """モックデータ（dicts のリスト）から normalized_video_reference を生成する。"""
    return [
        normalize_tiktok_video(v, account_id)
        for v in mock_videos
        if str(v.get("platform", "")).lower() == "tiktok"
        or str(v.get("content_type", "")).lower() == "video"
    ]


def collect_from_json_file(
    json_path: str,
    account_id: str,
) -> list[dict[str, Any]]:
    """JSON ファイルからモックデータを読み込んで正規化する。"""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        videos = [v for v in data if v.get("platform", "").lower() == "tiktok"]
    elif isinstance(data, dict):
        videos = data.get("tiktok", [])
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
