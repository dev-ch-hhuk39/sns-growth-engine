"""
content_mix_planner.py - 投稿種別ミックスプランナー（Phase 7.A）

single_post / thread_series / reference_based / video_clip_reference を
アカウントごとの比率で自動選択する。

禁止事項:
  - 実SNS投稿
  - READY/POSTED 化
  - beauty_account の実投稿
  - learning_rules の auto active 化
"""
from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MIX_CONFIG_PATH = os.path.join(_V2_ROOT, "config", "content_mix", "default_mix.json")

JST = timezone(timedelta(hours=9))

CONTENT_TYPES = [
    "single_post",
    "thread_series",
    "reference_based",
    "video_clip_reference",
    "original_hypothesis",
]


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _load_mix_config() -> dict:
    if os.path.isfile(_MIX_CONFIG_PATH):
        with open(_MIX_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_mix_ratio(
    account_id: str,
    platform: str,
    config: dict | None = None,
) -> dict[str, int]:
    """アカウント・プラットフォームの比率辞書を返す。合計は 100 に正規化しない（そのまま重みとして使用）。"""
    if config is None:
        config = _load_mix_config()
    accounts = config.get("accounts", {})
    if account_id in accounts and platform in accounts[account_id]:
        return dict(accounts[account_id][platform])
    defaults = config.get("default", {})
    if platform in defaults:
        return dict(defaults[platform])
    # フォールバック
    return {"single_post": 40, "thread_series": 30, "reference_based": 20, "video_clip_reference": 10, "original_hypothesis": 0}


def weighted_sample(
    ratios: dict[str, int],
    count: int,
    seed: int | None = None,
) -> list[str]:
    """比率辞書に基づいて count 件の content_type をランダムサンプリングする。"""
    rng = random.Random(seed)
    types = [k for k, v in ratios.items() if v > 0]
    weights = [ratios[k] for k in types]
    if not types:
        return []
    result = rng.choices(types, weights=weights, k=count)
    return result


def build_mix_plan_item(
    account_id: str,
    platform: str,
    content_type: str,
    status: str,
    plan_id: str,
    index: int,
) -> dict[str, Any]:
    return {
        "plan_item_id": f"cmp_{plan_id}_{index:03d}",
        "plan_id": plan_id,
        "account_id": account_id,
        "platform": platform,
        "content_type": content_type,
        "status": status,
        "planned_at": _now_jst(),
    }


def plan_content_mix(
    account_id: str,
    platform: str,
    count: int = 10,
    seed: int | None = None,
    config: dict | None = None,
    force_mode: str | None = None,
) -> dict[str, Any]:
    """アカウント・プラットフォームのコンテンツミックスプランを生成する。

    Args:
        account_id: アカウントID
        platform: "x" または "threads"
        count: 生成件数
        seed: ランダムシード（再現可能性のため）
        config: ミックス設定辞書（省略時はファイルから読む）
        force_mode: 強制的に単一モードを使う場合に指定

    Returns:
        plan辞書（plan_id, items, ratio_summary, safety_status を含む）
    """
    try:
        from accounts.account_config import load_account_config
        acct_cfg = load_account_config(account_id)
        is_draft_only = acct_cfg.is_draft_only()
        is_active = acct_cfg.is_active()
        platform_ok = acct_cfg.allows_platform(platform)
    except FileNotFoundError:
        is_draft_only = False
        is_active = True
        platform_ok = True

    safety_status = "OK"
    safety_notes: list[str] = []

    if is_draft_only:
        safety_status = "DRAFT_ONLY"
        safety_notes.append(f"{account_id} は draft_only アカウントです。全アイテムは WAITING_REVIEW で生成します。")

    if not platform_ok:
        safety_status = "PLATFORM_NOT_ALLOWED"
        safety_notes.append(f"{account_id} は {platform} に対応していません。")

    item_status = "WAITING_REVIEW" if is_draft_only else "PLANNED"

    plan_id = str(uuid.uuid4())[:8]

    if config is None:
        config = _load_mix_config()

    ratios = get_mix_ratio(account_id, platform, config)

    if force_mode and force_mode in CONTENT_TYPES:
        selected_modes = [force_mode] * count
    else:
        selected_modes = weighted_sample(ratios, count, seed=seed)

    # ratio_summary: 実際の選択比率
    ratio_summary: dict[str, int] = {}
    for mode in selected_modes:
        ratio_summary[mode] = ratio_summary.get(mode, 0) + 1

    items = [
        build_mix_plan_item(account_id, platform, mode, item_status, plan_id, i)
        for i, mode in enumerate(selected_modes)
    ]

    return {
        "plan_id": plan_id,
        "account_id": account_id,
        "platform": platform,
        "count": count,
        "seed": seed,
        "ratios_config": ratios,
        "selected_modes": selected_modes,
        "ratio_summary": ratio_summary,
        "items": items,
        "safety_status": safety_status,
        "safety_notes": safety_notes,
        "generated_jobs_count": len(items),
        "planned_at": _now_jst(),
    }


def build_generation_jobs_candidates(
    mix_plan: dict[str, Any],
    source_ids: list[str] | None = None,
    video_candidates_available: bool = False,
) -> dict[str, Any]:
    """content_mix_planからgeneration_jobs候補を作成する。

    content_type別にjobを分類する:
      - single_post / original_hypothesis → 通常投稿job
      - reference_based → 参考投稿ベースjob (source_ids必要)
      - thread_series → thread_series job
      - video_clip_reference → 動画候補がない場合NOT_READY/WARN

    Args:
        mix_plan: plan_content_mix()の出力
        source_ids: 参考に使うsource_idリスト（reference_based用）
        video_candidates_available: 動画候補が存在するか

    Returns:
        generation_jobs_candidates辞書
    """
    account_id = mix_plan.get("account_id", "")
    platform = mix_plan.get("platform", "x")
    safety_status = mix_plan.get("safety_status", "OK")
    is_draft_only = safety_status == "DRAFT_ONLY"

    jobs: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in mix_plan.get("items", []):
        ct = item.get("content_type", "single_post")
        item_id = item.get("plan_item_id", "")

        if ct in ("single_post", "original_hypothesis"):
            job_status = "WAITING_REVIEW" if is_draft_only else "PLANNED"
            jobs.append({
                "job_id": f"gj_{item_id}",
                "account_id": account_id,
                "platform": platform,
                "content_type": ct,
                "job_type": "standard_post",
                "status": job_status,
                "source_id": None,
                "plan_item_id": item_id,
            })

        elif ct == "reference_based":
            if source_ids:
                job_status = "WAITING_REVIEW" if is_draft_only else "PLANNED"
                jobs.append({
                    "job_id": f"gj_{item_id}",
                    "account_id": account_id,
                    "platform": platform,
                    "content_type": ct,
                    "job_type": "reference_post",
                    "status": job_status,
                    "source_ids": source_ids,
                    "plan_item_id": item_id,
                })
            else:
                jobs.append({
                    "job_id": f"gj_{item_id}",
                    "account_id": account_id,
                    "platform": platform,
                    "content_type": ct,
                    "job_type": "reference_post",
                    "status": "NOT_READY",
                    "reason": "source_ids未指定",
                    "plan_item_id": item_id,
                })
                warnings.append(f"{item_id}: reference_based だが source_ids が未指定")

        elif ct == "thread_series":
            job_status = "WAITING_REVIEW" if is_draft_only else "PLANNED"
            jobs.append({
                "job_id": f"gj_{item_id}",
                "account_id": account_id,
                "platform": platform,
                "content_type": ct,
                "job_type": "thread_series",
                "status": job_status,
                "source_id": None,
                "plan_item_id": item_id,
            })

        elif ct == "video_clip_reference":
            if video_candidates_available:
                job_status = "WAITING_REVIEW" if is_draft_only else "PLANNED"
                jobs.append({
                    "job_id": f"gj_{item_id}",
                    "account_id": account_id,
                    "platform": platform,
                    "content_type": ct,
                    "job_type": "video_clip_post",
                    "status": job_status,
                    "source_id": None,
                    "plan_item_id": item_id,
                })
            else:
                jobs.append({
                    "job_id": f"gj_{item_id}",
                    "account_id": account_id,
                    "platform": platform,
                    "content_type": ct,
                    "job_type": "video_clip_post",
                    "status": "NOT_READY",
                    "reason": "動画候補なし",
                    "plan_item_id": item_id,
                })
                warnings.append(f"{item_id}: video_clip_reference だが動画候補なし → NOT_READY")

        else:
            job_status = "WAITING_REVIEW" if is_draft_only else "PLANNED"
            jobs.append({
                "job_id": f"gj_{item_id}",
                "account_id": account_id,
                "platform": platform,
                "content_type": ct,
                "job_type": "unknown",
                "status": job_status,
                "plan_item_id": item_id,
            })

    planned = sum(1 for j in jobs if j["status"] == "PLANNED")
    waiting = sum(1 for j in jobs if j["status"] == "WAITING_REVIEW")
    not_ready = sum(1 for j in jobs if j["status"] == "NOT_READY")

    return {
        "plan_id": mix_plan.get("plan_id"),
        "account_id": account_id,
        "platform": platform,
        "total_jobs": len(jobs),
        "planned": planned,
        "waiting_review": waiting,
        "not_ready": not_ready,
        "jobs": jobs,
        "warnings": warnings,
        "created_at": _now_jst(),
    }
