"""
source_registry.py - Source Account / Video Source Registry（Phase 8）

外部参考アカウント・動画ソース・YouTube/TikTok/Threads/X sourceを管理する。
設定管理のみ。実API取得・scraping・外部download禁止。

禁止事項:
  - 実API取得
  - scraping
  - 外部download
  - source priority自動変更
  - beauty_accountのactive化/READY化
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_REGISTRY_PATH = os.path.join(
    _V2_ROOT, "config", "source_accounts", "default_sources.json"
)

SUPPORTED_PLATFORMS = [
    "x",
    "threads",
    "tiktok",
    "youtube",
    "youtube_shorts",
    "instagram_reels",
]

RIGHTS_POLICIES = ["reference_only", "owned", "licensed", "unknown"]
REUSE_POLICIES = ["reference_only", "transform_required", "no_reuse"]
MEDIA_POLICIES = [
    "do_not_download",
    "plan_only",
    "allow_download_with_confirmation",
    "allow_upload_with_confirmation",
]
COLLECTION_METHODS = [
    "manual_json",
    "manual_csv",
    "manual_url",
    "api_future",
    "scrape_disallowed",
    # Phase 9: Library/CLI-based fetchers
    "yt_dlp",
    "tiktok_to_ytdlp",
    "agent_reach",
    "last30days_skill",
    "youtube_transcript",
    "browser_export",
    "api_disabled",
]

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def load_registry(registry_path: str | None = None) -> list[dict[str, Any]]:
    """source registryをJSONから読み込む。"""
    path = registry_path or _DEFAULT_REGISTRY_PATH
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("sources", [])


def filter_sources(
    sources: list[dict[str, Any]],
    target_account_id: str | None = None,
    platform: str | None = None,
    active_only: bool = True,
    exclude_blocked: bool = True,
    content_type: str | None = None,
) -> list[dict[str, Any]]:
    """条件でsource一覧を絞り込む。"""
    result = sources
    if active_only:
        result = [s for s in result if s.get("active", False)]
    if exclude_blocked:
        result = [s for s in result if not s.get("blocked", False)]
    if target_account_id:
        result = [
            s for s in result
            if target_account_id in s.get("target_account_ids", [])
        ]
    if platform:
        result = [s for s in result if s.get("source_platform") == platform]
    if content_type:
        result = [
            s for s in result
            if content_type in s.get("allowed_content_types", [])
        ]
    return sorted(result, key=lambda s: s.get("priority", 99))


def assess_source_rights(source: dict[str, Any]) -> dict[str, Any]:
    """sourceのrights/reuse/media policyを評価する。"""
    rights = source.get("rights_policy", "unknown")
    reuse = source.get("reuse_policy", "reference_only")
    media = source.get("media_policy", "do_not_download")
    blocked = source.get("blocked", False)
    collection = source.get("collection_method", "manual_json")

    issues: list[str] = []
    review_required = False

    if blocked:
        issues.append("blocked=true: 収集不可")
    if rights == "unknown":
        issues.append("rights_policy=unknown: WAITING_REVIEW必須")
        review_required = True
    if reuse == "no_reuse":
        issues.append("reuse_policy=no_reuse: media利用不可")
    if media == "do_not_download":
        issues.append("media_policy=do_not_download: download禁止")
    if collection == "scrape_disallowed":
        issues.append("collection_method=scrape_disallowed: scraping禁止")

    return {
        "source_id": source.get("source_id"),
        "rights_policy": rights,
        "reuse_policy": reuse,
        "media_policy": media,
        "collection_method": collection,
        "blocked": blocked,
        "review_required": review_required,
        "issues": issues,
        "can_collect": not blocked and collection != "scrape_disallowed",
        "can_use_media": reuse != "no_reuse" and media not in ("do_not_download",),
        "status": "WAITING_REVIEW" if review_required else "OK",
    }


def build_collection_plan(
    sources: list[dict[str, Any]],
    target_account_id: str,
    platform: str | None = None,
    content_type: str | None = None,
    top_n: int = 5,
    dry_run: bool = True,
) -> dict[str, Any]:
    """source registryから収集計画を作成する。実収集はしない。"""
    active = filter_sources(
        sources,
        target_account_id=target_account_id,
        platform=platform,
        active_only=True,
        exclude_blocked=True,
        content_type=content_type,
    )
    selected: list[dict] = []
    skipped: list[dict] = []

    for s in active:
        assessment = assess_source_rights(s)
        if not assessment["can_collect"]:
            skipped.append({
                "source_id": s.get("source_id"),
                "source_name": s.get("source_name"),
                "skip_reason": assessment["issues"],
            })
            continue
        selected.append({
            "source_id": s.get("source_id"),
            "source_name": s.get("source_name"),
            "source_platform": s.get("source_platform"),
            "source_handle": s.get("source_handle"),
            "collection_method": s.get("collection_method"),
            "top_n": s.get("top_n", top_n),
            "rights_status": assessment["rights_policy"],
            "review_required": assessment["review_required"],
            "media_policy": assessment["media_policy"],
        })

    rights_summary = {
        "reference_only": sum(1 for s in selected if s["rights_status"] == "reference_only"),
        "unknown": sum(1 for s in selected if s["rights_status"] == "unknown"),
        "owned": sum(1 for s in selected if s["rights_status"] == "owned"),
        "licensed": sum(1 for s in selected if s["rights_status"] == "licensed"),
    }
    media_policy_summary = {
        "do_not_download": sum(1 for s in selected if s["media_policy"] == "do_not_download"),
        "plan_only": sum(1 for s in selected if s["media_policy"] == "plan_only"),
        "allow_download_with_confirmation": sum(
            1 for s in selected
            if s["media_policy"] == "allow_download_with_confirmation"
        ),
    }

    return {
        "target_account_id": target_account_id,
        "platform_filter": platform,
        "content_type_filter": content_type,
        "dry_run": dry_run,
        "created_at": _now_jst(),
        "selected_sources": selected,
        "skipped_sources": skipped,
        "skip_reasons": [item for s in skipped for item in s.get("skip_reason", [])],
        "collection_plan": [
            {
                "source_id": s["source_id"],
                "action": "manual_collection_required",
                "method": s["collection_method"],
                "top_n": s["top_n"],
            }
            for s in selected
        ],
        "rights_summary": rights_summary,
        "media_policy_summary": media_policy_summary,
        "next_action": (
            "手動JSON/CSV/URLからデータを投入してください"
            if selected
            else "active sourceがありません"
        ),
    }


def validate_registry(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """source registryの必須フィールドを検証する。"""
    issues: list[dict] = []
    required_fields = [
        "source_id", "source_name", "source_platform", "source_handle",
        "source_url", "target_account_ids", "collection_method",
        "rights_policy", "reuse_policy", "media_policy",
    ]
    seen_ids: set = set()
    for s in sources:
        sid = s.get("source_id", "")
        errs: list[str] = []
        for f in required_fields:
            if f not in s:
                errs.append(f"missing field: {f}")
        if sid in seen_ids:
            errs.append("duplicate source_id")
        if sid:
            seen_ids.add(sid)
        if s.get("source_platform") not in SUPPORTED_PLATFORMS:
            errs.append(f"unknown platform: {s.get('source_platform')}")
        if s.get("rights_policy") not in RIGHTS_POLICIES:
            errs.append(f"unknown rights_policy: {s.get('rights_policy')}")
        if s.get("reuse_policy") not in REUSE_POLICIES:
            errs.append(f"unknown reuse_policy: {s.get('reuse_policy')}")
        if s.get("media_policy") not in MEDIA_POLICIES:
            errs.append(f"unknown media_policy: {s.get('media_policy')}")
        if errs:
            issues.append({"source_id": sid, "errors": errs})
    return issues


def get_source_pdca_summary(
    source_id: str,
    posted_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """source単位のPDCA成果サマリを返す。自動変更なし。"""
    relevant = [
        r for r in posted_results
        if r.get("source_id") == source_id or r.get("source_account_id") == source_id
    ]
    if not relevant:
        return {
            "source_id": source_id,
            "count": 0,
            "avg_likes": 0.0,
            "avg_views": 0.0,
            "avg_er": 0.0,
            "win_rate": 0.0,
            "improvement_suggestion": None,
        }

    likes = [float(r.get("likes") or 0) for r in relevant]
    views = [float(r.get("views") or r.get("impressions") or 0) for r in relevant]
    avg_likes = sum(likes) / len(likes) if likes else 0.0
    avg_views = sum(views) / len(views) if views else 0.0
    avg_er = (
        sum(
            (likes[i] / views[i]) if views[i] > 0 else 0.0
            for i in range(len(relevant))
        )
        / len(relevant)
    ) if relevant else 0.0

    winners = sum(1 for r in relevant if float(r.get("likes") or 0) >= avg_likes)
    win_rate = winners / len(relevant) if relevant else 0.0

    suggestion = None
    if avg_er < 0.01 and len(relevant) >= 3:
        suggestion = {
            "type": "priority_down",
            "reason": f"平均ER {avg_er:.3f} が低い。priorityを下げることを検討してください。",
            "status": "WAITING_REVIEW",
            "auto_apply": False,
        }
    elif avg_er >= 0.05 and len(relevant) >= 3:
        suggestion = {
            "type": "priority_up",
            "reason": f"平均ER {avg_er:.3f} が高い。priorityを上げることを検討してください。",
            "status": "WAITING_REVIEW",
            "auto_apply": False,
        }

    return {
        "source_id": source_id,
        "count": len(relevant),
        "avg_likes": round(avg_likes, 2),
        "avg_views": round(avg_views, 2),
        "avg_er": round(avg_er, 4),
        "win_rate": round(win_rate, 4),
        "improvement_suggestion": suggestion,
    }
