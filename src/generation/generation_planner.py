"""
generation_planner.py — 8:2 投稿生成計画（Phase 2.13）

generation_jobs タブへのレコードを構築し、参考投稿候補を選択して
reference_based / original_hypothesis の比率で生成ジョブを計画する。
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))

# デフォルト設定
_DEFAULT_REFERENCE_RATIO = 0.8
_DEFAULT_ORIGINAL_RATIO = 0.2
_DEFAULT_DAILY_TARGET = 3
_DEFAULT_MIN_REFERENCE_SCORE = 50.0
_DEFAULT_AUTO_APPROVE_THRESHOLD = 80.0
_DEFAULT_MAX_REUSE = 3
_X_MAX_CHARS = 140
_THREADS_MAX_CHARS = 800


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


# ------------------------------------------------------------------ #
# 比率計算
# ------------------------------------------------------------------ #

def plan_daily_counts(daily_target: int, ratio: float) -> tuple[int, int]:
    """daily_target と ratio から reference_based / original_hypothesis の件数を計算する。

    Returns: (reference_count, original_count)
    """
    reference_count = round(daily_target * ratio)
    original_count = daily_target - reference_count
    return reference_count, original_count


def allocate_generation_modes(
    daily_target: int,
    ratio: float = _DEFAULT_REFERENCE_RATIO,
) -> list[str]:
    """daily_target 件分のモードリストを返す。

    例: daily_target=3, ratio=0.8 → ["reference_based", "reference_based", "original_hypothesis"]
    """
    ref_count, orig_count = plan_daily_counts(daily_target, ratio)
    modes = ["reference_based"] * ref_count + ["original_hypothesis"] * orig_count
    random.shuffle(modes)
    return modes


# ------------------------------------------------------------------ #
# 参考候補選択
# ------------------------------------------------------------------ #

def score_reference_candidate(score: dict) -> float:
    """参考投稿スコアレコードから候補選択スコアを計算する。"""
    buzz = float(score.get("buzz_score") or 0)
    account_pct = float(score.get("account_percentile") or 0)
    return buzz * 0.7 + account_pct * 0.3


def select_reference_candidates(
    scores: list[dict],
    min_score: float = _DEFAULT_MIN_REFERENCE_SCORE,
    count: int = 1,
    max_reuse: int = _DEFAULT_MAX_REUSE,
    used_reference_ids: set[str] | None = None,
) -> list[dict]:
    """参考投稿スコアリストから候補を選択する。

    Args:
        scores: reference_post_scores レコードのリスト
        min_score: buzz_score の最低閾値
        count: 必要な候補件数
        max_reuse: 同一参考投稿の最大再利用回数
        used_reference_ids: 既に使用済みの reference_post_id セット

    Returns:
        選択された score レコードのリスト
    """
    if used_reference_ids is None:
        used_reference_ids = set()

    eligible = [
        s for s in scores
        if float(s.get("buzz_score") or 0) >= min_score
        and str(s.get("reference_post_id", "")) not in used_reference_ids
    ]

    if not eligible:
        return []

    eligible.sort(key=score_reference_candidate, reverse=True)
    pool = eligible[: count * 3]

    if len(pool) <= count:
        return pool

    return random.sample(pool, count)


# ------------------------------------------------------------------ #
# ジョブレコード構築
# ------------------------------------------------------------------ #

def build_generation_job(
    account_id: str,
    platform: str,
    generation_mode: str = "reference_based",
    reference_based_ratio: float = _DEFAULT_REFERENCE_RATIO,
    original_hypothesis_ratio: float = _DEFAULT_ORIGINAL_RATIO,
    daily_target_count: int = _DEFAULT_DAILY_TARGET,
    min_reference_score: float = _DEFAULT_MIN_REFERENCE_SCORE,
    media_allowed: bool = True,
    max_reference_reuse_per_source: int = _DEFAULT_MAX_REUSE,
    auto_approve_threshold: float = _DEFAULT_AUTO_APPROVE_THRESHOLD,
    active: bool = True,
    notes: str = "",
    reference_post_id: str = "",
    reference_post_score_id: str = "",
    media_asset_id: str = "",
    status: str = "pending",
    generated_draft_id: str = "",
    generated_at: str = "",
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
        "reference_post_id": reference_post_id,
        "reference_post_score_id": reference_post_score_id,
        "media_asset_id": media_asset_id,
        "status": status,
        "generated_draft_id": generated_draft_id,
        "generated_at": generated_at,
    }


def build_generation_job_records(
    account_id: str,
    platform: str,
    reference_candidates: list[dict],
    daily_target_count: int = _DEFAULT_DAILY_TARGET,
    ratio: float = _DEFAULT_REFERENCE_RATIO,
    min_reference_score: float = _DEFAULT_MIN_REFERENCE_SCORE,
    auto_approve_threshold: float = _DEFAULT_AUTO_APPROVE_THRESHOLD,
    max_reference_reuse_per_source: int = _DEFAULT_MAX_REUSE,
) -> list[dict[str, Any]]:
    """参考候補リストからジョブレコード一覧を構築する。

    reference_based ジョブには参考投稿を1件ずつ割り当て、
    original_hypothesis ジョブは参考投稿なしで作成する。
    """
    modes = allocate_generation_modes(daily_target_count, ratio)
    jobs: list[dict[str, Any]] = []
    ref_iter = iter(reference_candidates)

    for mode in modes:
        if mode == "reference_based":
            candidate = next(ref_iter, None)
            if candidate is None:
                mode = "original_hypothesis"
                ref_post_id = ""
                score_id = ""
            else:
                ref_post_id = str(candidate.get("reference_post_id", ""))
                score_id = str(candidate.get("score_id", ""))
        else:
            ref_post_id = ""
            score_id = ""

        job = build_generation_job(
            account_id=account_id,
            platform=platform,
            generation_mode=mode,
            daily_target_count=daily_target_count,
            min_reference_score=min_reference_score,
            auto_approve_threshold=auto_approve_threshold,
            max_reference_reuse_per_source=max_reference_reuse_per_source,
            reference_post_id=ref_post_id,
            reference_post_score_id=score_id,
            status="pending",
        )
        jobs.append(job)

    return jobs


# ------------------------------------------------------------------ #
# 計画エントリーポイント
# ------------------------------------------------------------------ #

def plan_generation_jobs(
    account_id: str,
    platform: str,
    scores: list[dict],
    daily_target_count: int = _DEFAULT_DAILY_TARGET,
    ratio: float = _DEFAULT_REFERENCE_RATIO,
    min_reference_score: float = _DEFAULT_MIN_REFERENCE_SCORE,
    auto_approve_threshold: float = _DEFAULT_AUTO_APPROVE_THRESHOLD,
    max_reference_reuse_per_source: int = _DEFAULT_MAX_REUSE,
    used_reference_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """アカウント・プラットフォームの生成ジョブリストを返す。

    Args:
        account_id: v2 アカウントID
        platform: "x" または "threads"
        scores: reference_post_scores レコードのリスト
        daily_target_count: 1日あたり生成目標件数
        ratio: reference_based の比率（0.0〜1.0）
        min_reference_score: 参考投稿の最低スコア閾値
        auto_approve_threshold: 自動承認スコア閾値
        max_reference_reuse_per_source: 同一参考投稿の最大再利用回数
        used_reference_ids: 既使用の reference_post_id セット

    Returns:
        daily_target_count 件の generation_job レコードリスト
    """
    ref_count, _ = plan_daily_counts(daily_target_count, ratio)
    candidates = select_reference_candidates(
        scores=scores,
        min_score=min_reference_score,
        count=ref_count,
        max_reuse=max_reference_reuse_per_source,
        used_reference_ids=used_reference_ids,
    )
    return build_generation_job_records(
        account_id=account_id,
        platform=platform,
        reference_candidates=candidates,
        daily_target_count=daily_target_count,
        ratio=ratio,
        min_reference_score=min_reference_score,
        auto_approve_threshold=auto_approve_threshold,
        max_reference_reuse_per_source=max_reference_reuse_per_source,
    )


def create_generation_jobs_for_account(
    account_id: str,
    platforms: list[str],
    scores: list[dict],
    daily_target_count: int = _DEFAULT_DAILY_TARGET,
    ratio: float = _DEFAULT_REFERENCE_RATIO,
    min_reference_score: float = _DEFAULT_MIN_REFERENCE_SCORE,
    auto_approve_threshold: float = _DEFAULT_AUTO_APPROVE_THRESHOLD,
    max_reference_reuse_per_source: int = _DEFAULT_MAX_REUSE,
) -> list[dict[str, Any]]:
    """指定アカウントの全プラットフォームに対してジョブを生成する。"""
    all_jobs: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for platform in platforms:
        jobs = plan_generation_jobs(
            account_id=account_id,
            platform=platform,
            scores=scores,
            daily_target_count=daily_target_count,
            ratio=ratio,
            min_reference_score=min_reference_score,
            auto_approve_threshold=auto_approve_threshold,
            max_reference_reuse_per_source=max_reference_reuse_per_source,
            used_reference_ids=used_ids,
        )
        for j in jobs:
            if j.get("reference_post_id"):
                used_ids.add(j["reference_post_id"])
        all_jobs.extend(jobs)
    return all_jobs


def create_daily_generation_plan(
    accounts: list[dict],
    scores_by_account: dict[str, list[dict]],
    platforms: list[str] | None = None,
    daily_target_count: int = _DEFAULT_DAILY_TARGET,
    ratio: float = _DEFAULT_REFERENCE_RATIO,
    min_reference_score: float = _DEFAULT_MIN_REFERENCE_SCORE,
    auto_approve_threshold: float = _DEFAULT_AUTO_APPROVE_THRESHOLD,
) -> dict[str, list[dict[str, Any]]]:
    """全アカウントの日次生成計画を作成する。

    Returns:
        {account_id: [job_records, ...]}
    """
    if platforms is None:
        platforms = ["x", "threads"]

    plan: dict[str, list[dict[str, Any]]] = {}
    for account in accounts:
        account_id = str(account.get("account_id", ""))
        if not account_id:
            continue
        account_scores = scores_by_account.get(account_id, [])
        jobs = create_generation_jobs_for_account(
            account_id=account_id,
            platforms=platforms,
            scores=account_scores,
            daily_target_count=daily_target_count,
            ratio=ratio,
            min_reference_score=min_reference_score,
            auto_approve_threshold=auto_approve_threshold,
        )
        plan[account_id] = jobs
    return plan


# ------------------------------------------------------------------ #
# Sheets 書き込みヘルパー
# ------------------------------------------------------------------ #

def write_generation_job(client: Any, job: dict[str, Any]) -> None:
    """generation_jobs タブに1行を追記する。"""
    client.append_row("generation_jobs", job)
