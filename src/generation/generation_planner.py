"""
generation_planner.py — 8:2 投稿生成計画（Phase 2.8 最小実装）

generation_jobs タブへの1行データを構築し SheetsClient 経由で書き込む。
Phase 2.13 で reference_based / original_hypothesis の分岐ロジックを本実装する。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


# デフォルト設定
_DEFAULT_REFERENCE_RATIO = 0.8
_DEFAULT_ORIGINAL_RATIO = 0.2
_DEFAULT_DAILY_TARGET = 3
_DEFAULT_MIN_REFERENCE_SCORE = 50.0
_DEFAULT_AUTO_APPROVE_THRESHOLD = 80.0
_X_MAX_CHARS = 140
_THREADS_MAX_CHARS = 800


def build_generation_job(
    account_id: str,
    platform: str,
    generation_mode: str = "reference_based",
    reference_based_ratio: float = _DEFAULT_REFERENCE_RATIO,
    original_hypothesis_ratio: float = _DEFAULT_ORIGINAL_RATIO,
    daily_target_count: int = _DEFAULT_DAILY_TARGET,
    min_reference_score: float = _DEFAULT_MIN_REFERENCE_SCORE,
    media_allowed: bool = True,
    max_reference_reuse_per_source: int = 3,
    auto_approve_threshold: float = _DEFAULT_AUTO_APPROVE_THRESHOLD,
    active: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    """generation_jobs タブへの1行データを構築する。"""
    return {
        "job_id": str(uuid.uuid4()),
        "account_id": account_id,
        "platform": platform,
        "generation_mode": generation_mode,
        "reference_based_ratio": reference_based_ratio,
        "original_hypothesis_ratio": original_hypothesis_ratio,
        "daily_target_count": daily_target_count,
        "min_reference_score": min_reference_score,
        "media_allowed": "true" if media_allowed else "false",
        "max_reference_reuse_per_source": max_reference_reuse_per_source,
        "auto_approve_threshold": auto_approve_threshold,
        "x_max_chars": _X_MAX_CHARS,
        "threads_max_chars": _THREADS_MAX_CHARS,
        "active": "true" if active else "false",
        "notes": notes,
    }


def write_generation_job(client: Any, job: dict[str, Any]) -> None:
    """generation_jobs タブに1行を追記する。"""
    client.append_row("generation_jobs", job)


def plan_daily_counts(daily_target: int, ratio: float) -> tuple[int, int]:
    """daily_target と ratio から reference_based / original_hypothesis の件数を計算する。

    Returns: (reference_count, original_count)
    """
    reference_count = round(daily_target * ratio)
    original_count = daily_target - reference_count
    return reference_count, original_count
