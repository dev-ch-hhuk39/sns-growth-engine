"""
video_source_manager.py - 動画収集元（YouTube/TikTok）管理

reference_sources タブで管理するソース情報を読み書きし、
アカウント・プラットフォームごとのアクティブなソース一覧を提供する。

実際の動画収集は youtube_video_collector / tiktok_video_collector が行う。
このモジュールはソース定義の CRUD のみを担当する。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def build_source_id(account_id: str, platform: str, handle: str) -> str:
    """ソースIDを生成する（account_id + platform + handle から決定論的に生成）。"""
    safe_handle = handle.lstrip("@").replace("/", "_").replace(".", "_")
    return f"src-{account_id}-{platform}-{safe_handle}"


def normalize_source(raw: dict[str, Any]) -> dict[str, Any]:
    """ソース定義を正規化して reference_sources 行フォーマットに変換する。

    Args:
        raw: source_id / account_id / platform / source_url / handle / priority /
             active / collection_frequency / notes を含むdict

    Returns:
        reference_sources タブに保存可能な正規化済みdict
    """
    account_id = str(raw.get("account_id", ""))
    platform = str(raw.get("platform", "")).lower()
    handle = str(raw.get("handle", ""))

    source_id = raw.get("source_id") or build_source_id(account_id, platform, handle)

    return {
        "source_id": source_id,
        "account_id": account_id,
        "platform": platform,
        "source_url": str(raw.get("source_url", "")),
        "handle": handle,
        "priority": int(raw.get("priority", 5)),
        "active": str(raw.get("active", "TRUE")).upper(),
        "collection_frequency": str(raw.get("collection_frequency", "daily")),
        "last_collected_at": str(raw.get("last_collected_at", "")),
        "notes": str(raw.get("notes", "")),
    }


def get_active_sources(
    client: Any,
    account_id: str | None = None,
    platform: str | None = None,
) -> list[dict[str, Any]]:
    """アクティブなソース一覧を優先度順で返す。"""
    sources = client.get_reference_sources(
        account_id=account_id,
        platform=platform,
        active_only=True,
    )
    return sorted(sources, key=lambda s: int(s.get("priority", 5)))


def register_source(
    client: Any,
    source_def: dict[str, Any],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """ソース定義を reference_sources タブに登録する（冪等）。

    dry_run=True の場合は保存を行わずに正規化済みdictを返す。
    """
    normalized = normalize_source(source_def)
    if dry_run:
        print(f"[dry-run] register_source: source_id={normalized['source_id']!r} platform={normalized['platform']!r}")
        return normalized

    client.save_reference_source(normalized)
    return normalized


def mark_source_collected(
    client: Any,
    source_id: str,
    *,
    dry_run: bool = True,
) -> None:
    """ソースの last_collected_at を現在時刻に更新する。"""
    if dry_run:
        print(f"[dry-run] mark_source_collected: source_id={source_id!r}")
        return
    client.update_reference_source(source_id, last_collected_at=_now())
