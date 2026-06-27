#!/usr/bin/env python3
"""Recover production Google Sheets for Threads-first operation.

This script intentionally performs only Google Sheets setup/seed/verification.
It does not fetch, download, cut, upload, transcribe, or post to SNS.
Secret values are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_cloudinary_config, get_config  # noqa: E402
from publishers.threads_credentials import has_required_for_publish, resolve_credentials  # noqa: E402
from sheets_client import SheetsClient, TAB_DEFINITIONS, TAB_DISPLAY_NAMES  # noqa: E402

JST = timezone(timedelta(hours=9))

TARGET_TABS = [
    "accounts",
    "source_accounts",
    "reference_sources",
    "reference_posts",
    "source_account_posts",
    "content_categories",
    "content_mix_plans",
    "generation_jobs",
    "drafts",
    "social_derivatives",
    "thread_series",
    "queue",
    "posted_results",
    "media_assets",
    "video_transcripts",
    "video_clip_candidates",
    "pdca_runs",
    "prompt_improvement_suggestions",
    "learning_rules",
    "prompt_templates",
    "logs",
]


def now_iso() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _join(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(str(v) for v in value)
    return str(value or "")


def _display(logical: str) -> str:
    return TAB_DISPLAY_NAMES.get(logical, logical)


def _ws(client: SheetsClient, logical: str):
    cache = getattr(client, "_recovery_ws_cache", None)
    if isinstance(cache, dict) and logical in cache:
        return cache[logical]
    return client._ws(logical)


def _refresh_ws_cache(client: SheetsClient) -> None:
    worksheets = {ws.title: ws for ws in client._sh.worksheets()}
    cache = {}
    for logical in set(TARGET_TABS) | set(TAB_DEFINITIONS):
        title = _display(logical)
        if title in worksheets:
            cache[logical] = worksheets[title]
        elif logical in worksheets:
            cache[logical] = worksheets[logical]
    setattr(client, "_recovery_ws_cache", cache)


def _records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    return [dict(r) for r in _ws(client, logical).get_all_records()]


def _ensure_headers(client: SheetsClient, logical: str, headers: list[str]) -> list[str]:
    ws = _ws(client, logical)
    existing = ws.row_values(1)
    missing = [h for h in headers if h not in existing]
    if missing and not client.dry_run:
        next_col = len(existing) + 1
        required_cols = len(existing) + len(missing)
        if required_cols > ws.col_count:
            ws.resize(rows=ws.row_count, cols=max(required_cols + 10, ws.col_count + 20))
        col_letter = _col_letter(next_col)
        ws.update([[h] for h in missing], f"{col_letter}1", major_dimension="COLUMNS")
    return missing


def _upsert_many(client: SheetsClient, logical: str, key: str, rows_to_seed: list[dict[str, Any]]) -> dict[str, int]:
    ws = _ws(client, logical)
    headers = ws.row_values(1)
    if key not in headers:
        raise KeyError(f"{_display(logical)} missing key header: {key}")
    existing_rows = ws.get_all_records()
    existing_by_id = {
        str(existing.get(key, "")): (idx, existing)
        for idx, existing in enumerate(existing_rows, start=2)
        if str(existing.get(key, ""))
    }
    appends: list[list[str]] = []
    updated = 0
    added = 0
    for row in rows_to_seed:
        row_id = str(row.get(key, ""))
        if not row_id:
            raise ValueError(f"{_display(logical)} row missing key value: {key}")
        if row_id in existing_by_id:
            idx, existing = existing_by_id[row_id]
            merged = {**existing, **row}
            values = [str(merged.get(h, "")) for h in headers]
            if not client.dry_run:
                ws.update([values], f"A{idx}")
            updated += 1
        else:
            appends.append([str(row.get(h, "")) for h in headers])
            added += 1
    if appends and not client.dry_run:
        ws.append_rows(appends, value_input_option="USER_ENTERED")
    return {"added": added, "updated": updated}


def _audit_tabs(client: SheetsClient) -> dict[str, dict[str, Any]]:
    works = {ws.title: ws for ws in client._sh.worksheets()}
    result: dict[str, dict[str, Any]] = {}
    for logical in TARGET_TABS:
        title = _display(logical)
        ws = works.get(title)
        if ws is None:
            result[title] = {"exists": False, "header": False, "rows": 0, "cols": 0}
            continue
        values = ws.get_all_values()
        header = values[0] if values else []
        result[title] = {
            "exists": True,
            "header": bool(header),
            "rows": max(0, len(values) - 1),
            "cols": len(header),
        }
    return result


def account_rows() -> list[dict[str, Any]]:
    common = {
        "platform": "threads",
        "x_enabled": "false",
        "threads_enabled": "true",
        "active": "true",
        "status": "active",
        "tone": "アカウント別トンマナガイド準拠",
        "cta_type": "LINE_AND_DM",
        "cta_text": "相談はLINEまたはDMで",
        "line_cta_enabled": "true",
        "dm_cta_enabled": "true",
        "sns_dm_cta_enabled": "true",
        "auto_publish": "false",
        "default_queue_status": "WAITING_REVIEW",
        "timezone": "Asia/Tokyo",
        "post_time": "20:00",
    }
    return [
        {
            **common,
            "account_id": "night_scout",
            "account_name": "夜職スカウト",
            "target_persona": "キャバ嬢・夜職女性・これからキャバを始めたい女性",
            "main_genre": "夜職スカウト",
            "notes": "Threads中心。X自動投稿OFF。CTAはLINE+SNS DMを自然に使用。",
        },
        {
            **common,
            "account_id": "liver_manager",
            "account_name": "ライバーマネージャー",
            "target_persona": "TikTokライブ未経験者・既存ライバー・配信で稼ぎたい人",
            "main_genre": "ライバーマネジメント",
            "notes": "Threads中心。X自動投稿OFF。事務所営業っぽいCTAは禁止。",
        },
        {
            "account_id": "beauty_account",
            "account_name": "美容アカウント",
            "platform": "threads",
            "x_enabled": "false",
            "threads_enabled": "false",
            "active": "false",
            "status": "draft_only",
            "target_persona": "美容に興味がある女性",
            "tone": "draft_only。美容医療/薬機法/医療広告リスクレビュー必須。",
            "main_genre": "美容",
            "cta_type": "NONE",
            "cta_text": "",
            "line_cta_enabled": "false",
            "dm_cta_enabled": "false",
            "sns_dm_cta_enabled": "false",
            "auto_publish": "false",
            "default_queue_status": "DRAFT",
            "active": "false",
            "notes": "実投稿禁止。READY/POSTED化禁止。",
        },
    ]


def category_rows() -> list[dict[str, Any]]:
    ns = [
        "店選び",
        "指名/接客",
        "LINE対応",
        "同伴/アフター",
        "稼げる子の特徴",
        "夜職初心者向け",
        "メンタル/継続",
        "スカウト目線の注意点",
    ]
    lm = [
        "配信初心者向け",
        "コメント返し",
        "ファン化",
        "継続習慣",
        "配信時間/頻度",
        "TikTokライブの数字の見方",
        "事務所選び",
        "稼げるライバーの特徴",
    ]
    rows: list[dict[str, Any]] = []
    for i, name in enumerate(ns, start=1):
        rows.append({
            "category_id": f"recovery_ns_{i:02d}",
            "account_id": "night_scout",
            "category_name": name,
            "description": f"Threads運用初期カテゴリ: {name}",
            "weight": "1.0",
            "examples": name,
            "tags": "threads,recovery",
            "active": "TRUE",
        })
    for i, name in enumerate(lm, start=1):
        rows.append({
            "category_id": f"recovery_lm_{i:02d}",
            "account_id": "liver_manager",
            "category_name": name,
            "description": f"Threads運用初期カテゴリ: {name}",
            "weight": "1.0",
            "examples": name,
            "tags": "threads,recovery",
            "active": "TRUE",
        })
    rows.append({
        "category_id": "recovery_ba_01",
        "account_id": "beauty_account",
        "category_name": "draft_only_review",
        "description": "美容アカウントは下書きレビュー専用。実投稿対象外。",
        "weight": "0",
        "examples": "薬機法/医療広告リスクレビュー",
        "tags": "draft_only,blocked",
        "active": "FALSE",
    })
    return rows


def prompt_rows() -> list[dict[str, Any]]:
    created_at = now_iso()
    return [
        {
            "template_id": "night_scout_threads",
            "account_id": "night_scout",
            "template_name": "night_scout_threads",
            "version": "recovery-2026-06-24",
            "purpose": "Threads投稿生成",
            "prompt_text": (
                "夜職女性向けに、現場ノウハウと店選びの判断軸を具体的に書く。"
                "薄い応援・美容・求人LP調は禁止。CTAは毎回ではなく自然に、"
                "入れる場合は「詳しく聞きたい子はLINEかDMで相談してね」。"
            ),
            "active": "TRUE",
            "created_at": created_at,
            "notes": "CTA=LINE_AND_DM / Threads-first",
        },
        {
            "template_id": "night_scout_x",
            "account_id": "night_scout",
            "template_name": "night_scout_x",
            "version": "recovery-2026-06-24",
            "purpose": "X投稿生成",
            "prompt_text": "Xは一旦停止。生成してもDRAFT/WAITING_REVIEWまで。実投稿キューを作らない。",
            "active": "FALSE",
            "created_at": created_at,
            "notes": "X disabled",
        },
        {
            "template_id": "liver_manager_threads",
            "account_id": "liver_manager",
            "template_name": "liver_manager_threads",
            "version": "recovery-2026-06-24",
            "purpose": "Threads投稿生成",
            "prompt_text": (
                "TikTokライブの伸ばし方を数字・具体例・現場感で書く。"
                "誰でも稼げる、事務所営業っぽい表現、他社批判は禁止。CTAは自然に、"
                "入れる場合は「配信の伸ばし方を相談したい人はLINEかDMで聞いてね」。"
            ),
            "active": "TRUE",
            "created_at": created_at,
            "notes": "CTA=LINE_AND_DM / Threads-first",
        },
        {
            "template_id": "liver_manager_x",
            "account_id": "liver_manager",
            "template_name": "liver_manager_x",
            "version": "recovery-2026-06-24",
            "purpose": "X投稿生成",
            "prompt_text": "Xは一旦停止。生成してもDRAFT/WAITING_REVIEWまで。実投稿キューを作らない。",
            "active": "FALSE",
            "created_at": created_at,
            "notes": "X disabled",
        },
        {
            "template_id": "beauty_draft_only",
            "account_id": "beauty_account",
            "template_name": "beauty_draft_only",
            "version": "recovery-2026-06-24",
            "purpose": "美容draft_only",
            "prompt_text": "CTAなし。実投稿なし。医療効果断定、before/after断定、施術効果保証は禁止。",
            "active": "FALSE",
            "created_at": created_at,
            "notes": "draft_only / blocked",
        },
    ]


QUEUE_TEXTS = {
    "night_scout": [
        (
            "店選びで稼ぎはかなり変わる",
            "バック率だけ見て店を決める子ほど、あとで苦しくなる。客層、シフトの自由度、担当の動き方まで見ないと、同じ努力でも結果がズレるんだよね。\n\n詳しく聞きたい子はLINEかDMで相談してね。",
        ),
        (
            "指名が続く子はLINEが雑じゃない",
            "売れている子ほど、営業LINEをただ送っていない。相手が返しやすい温度で、会話の続きになる一言を置いている。接客は席を離れたあとも続いてる。",
        ),
        (
            "夜職初心者が最初に見るべきポイント",
            "最初の店で見るべきなのは、時給よりも教えてくれる環境。放置される店だと、伸びる前に自信だけ削られる。初心者ほど環境選びが大事。",
        ),
    ],
    "liver_manager": [
        (
            "配信は長さより戻ってきたくなる理由",
            "TikTokライブで伸びる人は、長時間やっているだけじゃない。コメントを拾う順番、名前の呼び方、ギフト後の反応でリスナーの戻り方が変わる。",
        ),
        (
            "未経験ライバーが最初に見る数字",
            "最初から売上だけ見ても判断を間違える。まず見るのは同接、コメント率、リピートしてくれる人の数。数字の見方がわかると改善点が見える。",
        ),
        (
            "事務所選びで見るべきなのは条件だけじゃない",
            "還元率だけで決めると、伸び悩んだ時に詰まる。配信の改善を一緒に見てくれるか、数字をもとに話せるかが大事。\n\n配信の伸ばし方を相談したい人はLINEかDMで聞いてね。",
        ),
    ],
}


def draft_social_queue_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    created = now_iso()
    drafts: list[dict[str, Any]] = []
    socials: list[dict[str, Any]] = []
    queues: list[dict[str, Any]] = []
    for account_id, entries in QUEUE_TEXTS.items():
        for i, (title, text) in enumerate(entries, start=1):
            draft_id = f"recovery_{account_id}_draft_{i:02d}"
            derivative_id = f"recovery_{account_id}_threads_{i:02d}"
            queue_id = f"recovery_{account_id}_queue_{i:02d}"
            drafts.append({
                "draft_id": draft_id,
                "created_at": created,
                "account_id": account_id,
                "title": title,
                "body_md": text,
                "content": text,
                "cta_text": "LINEまたはDM" if "LINE" in text or "DM" in text else "",
                "status": "WAITING_REVIEW",
                "generation_model": "manual_recovery_seed",
                "prompt_version": "recovery-2026-06-24",
                "brand_risk_score": "0",
                "post_mode": "threads_first",
                "generation_mode": "manual_seed",
                "media_strategy": "none",
                "media_reuse_risk": "low",
                "confidence_level": "medium",
                "ai_publish_recommendation": "WAITING_REVIEW",
                "notes": "Sheets recovery seed. X投稿なし。",
            })
            socials.append({
                "derivative_id": derivative_id,
                "draft_id": draft_id,
                "account_id": account_id,
                "platform": "threads",
                "text": text,
                "hashtags": "",
                "status": "WAITING_REVIEW",
                "reason": "Threads-first recovery seed",
                "created_at": created,
                "char_count": str(len(text)),
                "text_policy_status": "PASS",
                "media_strategy": "none",
            })
            queues.append({
                "queue_id": queue_id,
                "draft_id": draft_id,
                "account_id": account_id,
                "platform": "threads",
                "scheduled_at": "",
                "priority": str(i),
                "status": "WAITING_REVIEW" if i <= 2 else "PLANNED",
                "error": "",
                "created_at": created,
                "processed_at": "",
                "auto_publish": "false",
                "generation_mode": "manual_seed",
                "confidence_level": "medium",
                "ai_publish_recommendation": "WAITING_REVIEW",
                "text_policy_status": "PASS",
                "rights_status": "not_required",
                "permission_status": "not_required",
                "rights_review_required": "false",
                "media_reuse_risk": "low",
            })
    return drafts, socials, queues


def learning_rule_rows() -> list[dict[str, Any]]:
    created = now_iso()
    return [
        {
            "rule_id": f"recovery_{account_id}_initial_rule",
            "account_id": account_id,
            "insight_type": "initial_policy",
            "content": "Threads-first operation. Suggestions require human review before use.",
            "source_draft_id": "",
            "confidence": "0.5",
            "applied_count": "0",
            "created_at": created,
            "active": "false",
            "auto_apply": "false",
            "status": "WAITING_REVIEW",
        }
        for account_id in ["night_scout", "liver_manager", "beauty_account"]
    ]


def generation_job_rows() -> list[dict[str, Any]]:
    return [
        {
            "job_id": f"recovery_{account_id}_threads_job",
            "account_id": account_id,
            "platform": "threads",
            "generation_mode": "threads_first_manual_seed",
            "reference_based_ratio": "0.8",
            "original_hypothesis_ratio": "0.2",
            "daily_target_count": "1",
            "min_reference_score": "0.5",
            "media_allowed": "false",
            "max_reference_reuse_per_source": "1",
            "auto_approve_threshold": "999",
            "x_max_chars": "0",
            "threads_max_chars": "500",
            "active": "TRUE",
            "status": "PLANNED",
            "notes": "Threads-first seed. X disabled. auto_publish=false.",
        }
        for account_id in ["night_scout", "liver_manager"]
    ]


def content_mix_rows() -> list[dict[str, Any]]:
    created = now_iso()
    return [
        {
            "plan_id": f"recovery_{account_id}_threads_mix",
            "account_id": account_id,
            "platform": "threads",
            "content_type": "threads_first",
            "status": "PLANNED",
            "seed": "manual_recovery",
            "force_mode": "false",
            "planned_at": created,
            "notes": "X disabled. No automatic source priority change.",
        }
        for account_id in ["night_scout", "liver_manager"]
    ]


def posted_result_recovery_row() -> dict[str, Any]:
    created = now_iso()
    return {
        "result_id": "recovery_threads_initial_night_scout",
        "draft_id": "manual_threads_initial_recovered",
        "account_id": "night_scout",
        "posted_at": created,
        "note_url": "",
        "title": "Threads初回投稿記録（復旧登録）",
        "measurement_window": "manual_recovery",
        "views": "0",
        "likes": "0",
        "comments": "0",
        "follows": "0",
        "profile_clicks": "0",
        "line_adds": "0",
        "applications": "0",
        "site_registrations": "0",
        "screening_requests": "0",
        "sales": "0",
        "manual_memo": "過去に成功済みのThreads初回投稿をSheets復旧用に再登録。今回の新規投稿ではない。",
        "collected_at": created,
        "platform": "threads",
        "external_post_id": "RECOVERED_MANUAL",
        "post_url": "",
        "status": "RECOVERED",
        "queue_id": "",
        "derivative_id": "",
        "metrics_status": "MANUAL_PENDING",
        "real_post": "false",
        "media_used": "false",
        "posted_text": "",
        "source_queue_status": "",
        "save_source": "recover_production_sheets_threads_first",
        "created_by": "recover_production_sheets_threads_first",
    }


def source_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text())
    rows_accounts: list[dict[str, Any]] = []
    rows_video: list[dict[str, Any]] = []
    for src in data.get("sources", []):
        targets = src.get("target_account_ids") or []
        account_id = targets[0] if targets else ""
        platform = str(src.get("source_platform", ""))
        is_beauty = account_id == "beauty_account"
        is_x = platform == "x"
        blocked = is_beauty
        active = "false" if blocked or is_x else str(bool(src.get("active", False))).lower()
        fetch_enabled = "false"
        note_bits = [
            str(src.get("notes", "")),
            "auto_priority_change_allowed=false",
            "download/cut/upload=false",
        ]
        if is_x:
            note_bits.append("X posting disabled; source is reference-only")
        if is_beauty:
            note_bits.append("BLOCKED_BEAUTY_ACCOUNT")
        common = {
            "source_id": src.get("source_id"),
            "source_name": src.get("source_name", src.get("source_id")),
            "source_platform": platform,
            "source_handle": src.get("source_handle", ""),
            "source_url": src.get("source_url", ""),
            "target_account_ids": _join(targets),
            "collection_method": src.get("collection_method", ""),
            "active": active,
            "blocked": str(blocked).lower(),
            "priority": str(src.get("priority", "50")),
            "min_engagement_rate": str(src.get("min_engagement_rate", "")),
            "min_views": str(src.get("min_views", "")),
            "top_n": str(src.get("top_n", "")),
            "rights_policy": src.get("rights_policy", "reference_only"),
            "reuse_policy": src.get("reuse_policy", "reference_only"),
            "media_policy": src.get("media_policy", "do_not_download"),
            "notes": " / ".join(x for x in note_bits if x),
            "created_at": src.get("created_at", now_iso()),
            "updated_at": now_iso(),
            "source_category": _join(src.get("source_category", "")),
            "candidate_status": "BLOCKED_BEAUTY_ACCOUNT" if is_beauty else src.get("candidate_status", "candidate"),
            "fetch_enabled": fetch_enabled,
            "allow_network_fetch": str(bool(src.get("allow_network_fetch", True))).lower(),
            "allow_download": "false",
            "allow_cut": "false",
            "allow_upload": "false",
            "auto_priority_change_allowed": "false",
        }
        rows_accounts.append(common)
        if platform in {"youtube", "tiktok"}:
            rows_video.append({
                "source_id": src.get("source_id"),
                "account_id": account_id,
                "platform": platform,
                "source_url": src.get("source_url", ""),
                "handle": src.get("source_handle", ""),
                "priority": str(src.get("priority", "50")),
                "active": active,
                "collection_frequency": "manual_review",
                "last_collected_at": "",
                "notes": common["notes"],
                "source_category": common["source_category"],
                "collection_method": src.get("collection_method", ""),
                "candidate_status": common["candidate_status"],
                "fetch_enabled": fetch_enabled,
                "allow_network_fetch": common["allow_network_fetch"],
                "rights_policy": common["rights_policy"],
                "reuse_policy": common["reuse_policy"],
                "media_policy": common["media_policy"],
                "allow_download": "false",
                "allow_cut": "false",
                "allow_upload": "false",
                "auto_priority_change_allowed": "false",
                "blocked": str(blocked).lower(),
            })
    return rows_accounts, rows_video


def log_row(summary: str) -> dict[str, Any]:
    return {
        "log_id": f"sheets_recovery_{datetime.now(JST).strftime('%Y%m%d_%H%M%S')}",
        "timestamp": now_iso(),
        "account_id": "system",
        "operation": "sheets_recovery_seed",
        "level": "INFO",
        "status": "DONE",
        "message": summary,
        "details": "No fetch/download/cut/upload/transcription/post executed.",
    }


def run_recovery(client: SheetsClient) -> dict[str, Any]:
    before = _audit_tabs(client)
    client.setup_all()
    _refresh_ws_cache(client)
    header_added: dict[str, list[str]] = {}

    operations: dict[str, dict[str, int]] = {}

    def seed(logical: str, key: str, rows: list[dict[str, Any]]) -> None:
        operations[_display(logical)] = _upsert_many(client, logical, key, rows)

    seed("accounts", "account_id", account_rows())
    seed("content_categories", "category_id", category_rows())
    seed("prompt_templates", "template_id", prompt_rows())
    src_account_rows, src_video_rows = source_rows()
    seed("source_accounts", "source_id", src_account_rows)
    seed("reference_sources", "source_id", src_video_rows)
    seed("generation_jobs", "job_id", generation_job_rows())
    seed("content_mix_plans", "plan_id", content_mix_rows())
    drafts, socials, queues = draft_social_queue_rows()
    seed("drafts", "draft_id", drafts)
    seed("social_derivatives", "derivative_id", socials)
    seed("queue", "queue_id", queues)
    seed("learning_rules", "rule_id", learning_rule_rows())

    posted = _records(client, "posted_results")
    has_threads_result = any(
        str(r.get("platform", "")).lower() == "threads"
        or "threads" in str(r.get("manual_memo", "")).lower()
        for r in posted
    )
    if not has_threads_result:
        seed("posted_results", "result_id", [posted_result_recovery_row()])
    else:
        operations[_display("posted_results")] = {"added": 0, "updated": 0}

    backfilled = backfill_posted_results(client)
    if backfilled:
        operations[_display("posted_results")]["updated"] += backfilled

    seed("logs", "log_id", [log_row("production sheets recovered for Threads-first operation")])
    verification = verify_state(client)
    return {
        "before": before,
        "after": {},
        "header_added": header_added,
        "operations": operations,
        "verification": verification,
        "credentials": credential_status(),
    }


def credential_status() -> dict[str, Any]:
    threads: dict[str, Any] = {}
    for account_id in ["night_scout", "liver_manager", "beauty_account"]:
        creds = resolve_credentials(account_id)
        ok, reason = has_required_for_publish(creds)
        threads[account_id] = {
            "publish_credentials": "SET" if ok else "MISSING",
            "reason": "" if ok else reason,
        }
    cloudinary = get_cloudinary_config()
    return {
        "threads": threads,
        "cloudinary": {
            "cloud_name": "SET" if cloudinary.get("cloud_name") else "MISSING",
            "api_key": "SET" if cloudinary.get("api_key") else "MISSING",
            "api_secret": "SET" if cloudinary.get("api_secret_set") else "MISSING",
            "allow_upload": bool(cloudinary.get("allow_upload")),
        },
    }


def backfill_posted_results(client: SheetsClient) -> int:
    ws = _ws(client, "posted_results")
    headers = ws.row_values(1)
    rows = ws.get_all_records()
    updated = 0
    allowed_status = {"POSTED", "RECOVERED"}
    for idx, row in enumerate(rows, start=2):
        status = str(row.get("status", "")).upper()
        platform = str(row.get("platform", "")).lower()
        if status not in allowed_status and platform != "threads":
            continue
        changes: dict[str, str] = {}
        if "platform" in headers and not platform:
            changes["platform"] = "threads"
        if "status" in headers and not status:
            changes["status"] = "RECOVERED"
        if "metrics_status" in headers and not str(row.get("metrics_status", "")).strip():
            changes["metrics_status"] = "PENDING" if status == "POSTED" else "MANUAL_PENDING"
        if "real_post" in headers and not str(row.get("real_post", "")).strip():
            changes["real_post"] = "true"
        if "media_used" in headers and not str(row.get("media_used", "")).strip():
            changes["media_used"] = "false"
        if "save_source" in headers and not str(row.get("save_source", "")).strip():
            changes["save_source"] = "backfill_recover_production_sheets"
        if "created_by" in headers and not str(row.get("created_by", "")).strip():
            changes["created_by"] = "recover_production_sheets_threads_first"
        if changes and not client.dry_run:
            for field, value in changes.items():
                ws.update_cell(idx, headers.index(field) + 1, value)
            updated += 1
    return updated


def verify_state(client: SheetsClient) -> dict[str, Any]:
    accounts = {r.get("account_id"): r for r in _records(client, "accounts")}
    categories = _records(client, "content_categories")
    prompts = _records(client, "prompt_templates")
    queue = _records(client, "queue")
    posted = _records(client, "posted_results")
    learning = _records(client, "learning_rules")
    media = _records(client, "media_assets")
    source_accounts = _records(client, "source_accounts")
    reference_sources = _records(client, "reference_sources")
    social = _records(client, "social_derivatives")
    drafts = _records(client, "drafts")
    suggestions = _records(client, "prompt_improvement_suggestions")

    # --- media 承認・Cloudinary upload の整合（承認ゲートの不変条件を verify）---
    from media.queue_media_attach import is_media_rights_clear, resolve_media_url

    def _approved(asset: dict[str, Any]) -> bool:
        return (
            str(asset.get("approval_status", "")).strip().upper() == "APPROVED"
            or str(asset.get("status", "")).strip().upper() == "SELF_GENERATED"
        )

    # APPROVED な media は必ず権利クリアであること（no_reuse/high/plan_only 等を承認しない）
    approved_not_clear = [
        r for r in media
        if str(r.get("approval_status", "")).strip().upper() == "APPROVED"
        and not is_media_rights_clear(r)
    ]
    # upload 済み（cloudinary_url 等あり / upload_status=UPLOADED）の media は承認済みのみ
    uploaded_unapproved = [
        r for r in media
        if (resolve_media_url(r) or str(r.get("upload_status", "")).upper() == "UPLOADED")
        and not _approved(r)
    ]

    # --- metrics ループの安全（生成候補が worker に拾われない）---
    metrics_candidate_postable = [
        r for r in queue
        if str(r.get("generation_mode", "")).strip() == "metrics_driven_candidate"
        and str(r.get("status", "")).upper() in {"WAITING_REVIEW", "PLANNED"}
    ]
    # metrics 由来の改善提案は WAITING_REVIEW（自動適用しない）
    metrics_sugg_sources = {"import_threads_metrics_manual", "generate_next_queue_from_metrics"}
    metrics_sugg_not_waiting = [
        r for r in suggestions
        if str(r.get("source", "")).strip() in metrics_sugg_sources
        and str(r.get("status", "")).strip().upper() != "WAITING_REVIEW"
    ]

    def q_count(account_id: str) -> int:
        return sum(
            1 for r in queue
            if r.get("account_id") == account_id
            and str(r.get("platform", "")).lower() == "threads"
            and str(r.get("status", "")).upper() in {"WAITING_REVIEW", "PLANNED"}
        )

    unapproved_uploads = [
        r for r in media
        if str(r.get("allow_upload", "")).lower() == "true"
        or str(r.get("upload_status", "")).upper() in {"READY", "UPLOADED"}
    ]
    unsafe_sources = [
        r for r in source_accounts
        if str(r.get("allow_download", "")).lower() == "true"
        or str(r.get("allow_cut", "")).lower() == "true"
        or str(r.get("allow_upload", "")).lower() == "true"
        or str(r.get("auto_priority_change_allowed", "")).lower() == "true"
    ]
    threads_posted_or_recovered = [
        r for r in posted
        if str(r.get("platform", "")).lower() == "threads"
        and str(r.get("status", "")).upper() in {"POSTED", "RECOVERED"}
    ]
    posted_threads = [
        r for r in posted
        if str(r.get("platform", "")).lower() == "threads"
        and str(r.get("status", "")).upper() == "POSTED"
    ]
    allowed_metrics = {"PENDING", "MEASURED", "MANUAL_PENDING"}
    queue_by_id = {str(r.get("queue_id", "")): r for r in queue if str(r.get("queue_id", ""))}
    posted_by_queue = {str(r.get("queue_id", "")): r for r in posted if str(r.get("queue_id", ""))}
    queue_posted_rows = [r for r in queue if str(r.get("status", "")).upper() == "POSTED"]
    queue_consistency_ok = all(
        str(r.get("queue_id", "")) in queue_by_id
        for r in posted
        if str(r.get("queue_id", ""))
    )
    queue_posted_has_result = all(
        str(r.get("queue_id", "")) in posted_by_queue
        for r in queue_posted_rows
        if str(r.get("queue_id", ""))
    )
    post_url_or_pending_ok = all(
        bool(str(r.get("post_url", "")).strip())
        or "permalink_pending=true" in str(r.get("manual_memo", "")).lower()
        or "permalink_pending=true" in str(r.get("notes", "")).lower()
        for r in posted_threads
    )
    duplicate_seen: set[tuple[str, str, str]] = set()
    duplicate_found = False
    for row in posted_threads:
        text = str(row.get("posted_text", "")).strip()
        if not text:
            continue
        key = (str(row.get("account_id", "")), "threads", text)
        if key in duplicate_seen:
            duplicate_found = True
            break
        duplicate_seen.add(key)
    posted_save_failed = [
        r for r in queue
        if str(r.get("status", "")).upper() == "POSTED_SAVE_FAILED"
    ]
    # キュー件数（投稿消費後は 1〜2 件になりうる — WARN だが FAIL にしない）
    ns_count = q_count("night_scout")
    lm_count = q_count("liver_manager")
    REFILL_THRESHOLD = 3

    # WARN / refill 判定（queue が 1〜2 件の場合）
    warning_list: list[str] = []
    refill_needed_accounts: list[str] = []
    recommended_actions: list[str] = []
    if 0 < ns_count < REFILL_THRESHOLD:
        warning_list.append(f"queue_night_scout_low: count={ns_count} (recommend refill to {REFILL_THRESHOLD})")
        refill_needed_accounts.append("night_scout")
        recommended_actions.append(f"python3 scripts/refill_threads_queue.py --account-id night_scout --count {REFILL_THRESHOLD - ns_count}")
    if 0 < lm_count < REFILL_THRESHOLD:
        warning_list.append(f"queue_liver_manager_low: count={lm_count} (recommend refill to {REFILL_THRESHOLD})")
        refill_needed_accounts.append("liver_manager")
        recommended_actions.append(f"python3 scripts/refill_threads_queue.py --account-id liver_manager --count {REFILL_THRESHOLD - lm_count}")
    if len(posted_save_failed) > 0:
        warning_list.append(f"posted_save_failed_count: {len(posted_save_failed)} (run recover_orphan_threads_post.py)")

    # RECOVERED 行の未補完フィールド WARN
    recovered_missing_ext_id = [
        r for r in threads_posted_or_recovered
        if str(r.get("status", "")).upper() == "RECOVERED"
        and not str(r.get("external_post_id", "")).strip()
    ]
    if recovered_missing_ext_id:
        warning_list.append(f"recovered_missing_external_post_id: count={len(recovered_missing_ext_id)}")
        recommended_actions.append("recover_orphan_threads_post.py --apply --external-post-id <id> で更新してください")

    checks = {
        "accounts_3_present": all(a in accounts for a in ["night_scout", "liver_manager", "beauty_account"]),
        "night_scout_cta": accounts.get("night_scout", {}).get("cta_type") == "LINE_AND_DM",
        "liver_manager_cta": accounts.get("liver_manager", {}).get("cta_type") == "LINE_AND_DM",
        "beauty_cta_none": accounts.get("beauty_account", {}).get("cta_type") == "NONE",
        "beauty_inactive": not _bool(accounts.get("beauty_account", {}).get("active")),
        "categories_night_scout_8": sum(1 for r in categories if r.get("account_id") == "night_scout") >= 8,
        "categories_liver_manager_8": sum(1 for r in categories if r.get("account_id") == "liver_manager") >= 8,
        "prompts_5": len(prompts) >= 5,
        # FAIL: queue が 0 件なら即 FAIL。1〜2 件は WARN（上記 warning_list に追加済み）
        "queue_night_scout_min1": ns_count >= 1,
        "queue_liver_manager_min1": lm_count >= 1,
        "queue_beauty_0": q_count("beauty_account") == 0,
        "posted_threads_result": any(
            str(r.get("platform", "")).lower() == "threads"
            or "threads" in str(r.get("manual_memo", "")).lower()
            for r in posted
        ),
        "posted_night_scout_threads_exists": any(
            r.get("account_id") == "night_scout" for r in threads_posted_or_recovered
        ),
        "posted_liver_manager_threads_posted": any(
            r.get("account_id") == "liver_manager" for r in posted_threads
        ),
        "posted_rows_have_external_post_id": all(
            bool(str(r.get("external_post_id", "")).strip()) for r in posted_threads
        ),
        "posted_rows_have_post_url_or_permalink_pending": post_url_or_pending_ok,
        "posted_rows_platform_threads": all(
            str(r.get("platform", "")).lower() == "threads" for r in posted_threads
        ),
        "posted_rows_status_posted": all(
            str(r.get("status", "")).upper() == "POSTED" for r in posted_threads
        ),
        "posted_metrics_status_allowed": all(
            str(r.get("metrics_status", "")).upper() in allowed_metrics for r in threads_posted_or_recovered
        ),
        "posted_real_post_true": all(
            str(r.get("real_post", "")).lower() == "true" for r in posted_threads
        ),
        "posted_media_used_false": all(
            str(r.get("media_used", "")).lower() == "false" for r in posted_threads
        ),
        "posted_queue_id_consistent": queue_consistency_ok,
        "queue_posted_has_posted_result": queue_posted_has_result,
        "posted_duplicate_text_absent": not duplicate_found,
        "learning_inactive": all(not _bool(r.get("active")) for r in learning),
        "learning_auto_apply_false": all(not _bool(r.get("auto_apply")) for r in learning),
        "media_no_unapproved_upload": not unapproved_uploads,
        "media_approved_rows_rights_clear": not approved_not_clear,
        "media_uploaded_only_if_approved": not uploaded_unapproved,
        "metrics_candidates_not_postable": not metrics_candidate_postable,
        "metrics_suggestions_waiting_review": not metrics_sugg_not_waiting,
        "source_registry_reflected": len(source_accounts) >= len(source_rows()[0]),
        "video_sources_reflected": len(reference_sources) >= len(source_rows()[1]),
        "source_media_policy_safe": not unsafe_sources,
        "x_queue_absent": not any(str(r.get("platform", "")).lower() == "x" for r in queue),
        "drafts_seeded": len([r for r in drafts if str(r.get("draft_id", "")).startswith("recovery_")]) >= 6,
        "social_threads_seeded": len([r for r in social if str(r.get("platform", "")).lower() == "threads"]) >= 6,
    }
    return {
        "checks": checks,
        "passed": sum(1 for ok in checks.values() if ok),
        "failed": [k for k, ok in checks.items() if not ok],
        "warnings": {
            "posted_save_failed_count": len(posted_save_failed),
            "warning_list": warning_list,
            "refill_needed_accounts": refill_needed_accounts,
            "recommended_actions": recommended_actions,
        },
        "counts": {
            "accounts": len(accounts),
            "categories": len(categories),
            "prompt_templates": len(prompts),
            "source_accounts": len(source_accounts),
            "reference_sources": len(reference_sources),
            "drafts": len(drafts),
            "social_derivatives": len(social),
            "queue_night_scout": q_count("night_scout"),
            "queue_liver_manager": q_count("liver_manager"),
            "queue_beauty": q_count("beauty_account"),
            "posted_results": len(posted),
            "learning_rules": len(learning),
            "media_assets": len(media),
            "prompt_improvement_suggestions": len(suggestions),
        },
    }


def _col_letter(n: int) -> str:
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover production Sheets for Threads-first operation")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Sheets")
    parser.add_argument("--audit-only", action="store_true", help="Only read tab state")
    parser.add_argument("--verify-only", action="store_true", help="Only run read-after-write verification")
    parser.add_argument("--json", action="store_true", help="Print compact JSON summary")
    args = parser.parse_args()

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=args.dry_run)
    if args.audit_only:
        result = {"audit": _audit_tabs(client), "credentials": credential_status()}
    elif args.verify_only:
        _refresh_ws_cache(client)
        result = {"verification": verify_state(client), "credentials": credential_status()}
    else:
        result = run_recovery(client)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=== Sheets Recovery Summary ===")
        if "before" in result:
            empty_before = [name for name, info in result["before"].items() if info["exists"] and info["rows"] == 0]
            print(f"empty_tabs_before={','.join(empty_before)}")
            print(f"header_added_tabs={len(result['header_added'])}")
            for tab, stats in result["operations"].items():
                print(f"{tab}: added={stats['added']} updated={stats['updated']}")
            verification = result["verification"]
            print(f"verification_passed={verification['passed']} failed={len(verification['failed'])}")
            if verification["failed"]:
                print("failed_checks=" + ",".join(verification["failed"]))
            warn_data = verification.get("warnings", {})
            warn_list = warn_data.get("warning_list", [])
            refill = warn_data.get("refill_needed_accounts", [])
            if warn_list:
                print("warnings=" + "; ".join(warn_list))
            if refill:
                print("refill_needed_accounts=" + ",".join(refill))
            for key, value in verification["counts"].items():
                print(f"count_{key}={value}")
        elif "audit" in result:
            for tab, info in result["audit"].items():
                print(f"{tab}: exists={info['exists']} header={info['header']} rows={info['rows']} cols={info['cols']}")
        else:
            verification = result["verification"]
            print(f"verification_passed={verification['passed']} failed={len(verification['failed'])}")
            if verification["failed"]:
                print("failed_checks=" + ",".join(verification["failed"]))
            warn_data = verification.get("warnings", {})
            warn_list = warn_data.get("warning_list", [])
            refill = warn_data.get("refill_needed_accounts", [])
            if warn_list:
                print("warnings=" + "; ".join(warn_list))
            if refill:
                print("refill_needed_accounts=" + ",".join(refill))
            for key, value in verification["counts"].items():
                print(f"count_{key}={value}")
        creds = result["credentials"]
        for account_id, status in creds["threads"].items():
            print(f"threads_credentials_{account_id}={status['publish_credentials']}")
        cloudinary = creds["cloudinary"]
        print(
            "cloudinary="
            f"cloud_name:{cloudinary['cloud_name']},"
            f"api_key:{cloudinary['api_key']},"
            f"api_secret:{cloudinary['api_secret']},"
            f"allow_upload:{str(cloudinary['allow_upload']).lower()}"
        )

    if args.audit_only:
        return 0
    failed = result["verification"]["failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
