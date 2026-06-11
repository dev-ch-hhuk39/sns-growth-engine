"""
account_config.py - アカウント設定ローダー（Phase 6.0）

config/accounts/{account_id}.json を読み込み AccountConfig を返す。
forbidden_keywords/themes は seeds.py との後方互換を保ちながらマージする。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ACCOUNTS_DIR = os.path.join(_V2_ROOT, "config", "accounts")


@dataclass
class AccountConfig:
    account_id: str
    display_name: str
    status: str  # active / draft_only / inactive
    platforms: list[str]
    persona: str
    target_audience: str
    primary_goal: str
    secondary_goals: list[str]
    tone: str
    first_person: str
    content_categories: list[str]
    forbidden_themes: list[str]
    forbidden_keywords: list[str]
    platform_policy: dict[str, Any]
    cta_policy: dict[str, Any]
    reference_source_policy: dict[str, Any]
    video_policy: dict[str, Any]
    thread_series_policy: dict[str, Any]
    learning_policy: dict[str, Any]
    safety_policy: dict[str, Any]

    def is_active(self) -> bool:
        return self.status == "active"

    def is_draft_only(self) -> bool:
        return self.status == "draft_only"

    def allows_platform(self, platform: str) -> bool:
        return platform in self.platforms

    def get_char_limits(self, platform: str) -> dict[str, int]:
        policy = self.platform_policy.get(platform, {})
        return {
            "soft": policy.get("char_limit_soft", 120 if platform == "x" else 500),
            "hard": policy.get("char_limit_hard", 140 if platform == "x" else 800),
        }


def _merge_seeds_forbidden(account_id: str, cfg: dict) -> tuple[list[str], list[str]]:
    """seeds.py の forbidden データと JSON の値をマージする（JSON 優先）。"""
    try:
        from seeds import ACCOUNT_FORBIDDEN_KEYWORDS, ACCOUNT_FORBIDDEN_THEMES
        seeds_kw = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
        seeds_th = ACCOUNT_FORBIDDEN_THEMES.get(account_id, [])
    except ImportError:
        seeds_kw, seeds_th = [], []

    json_kw = cfg.get("forbidden_keywords", [])
    json_th = cfg.get("forbidden_themes", [])

    merged_kw = list(dict.fromkeys(json_kw + [k for k in seeds_kw if k not in json_kw]))
    merged_th = list(dict.fromkeys(json_th + [t for t in seeds_th if t not in json_th]))
    return merged_kw, merged_th


@lru_cache(maxsize=32)
def load_account_config(account_id: str) -> AccountConfig:
    """config/accounts/{account_id}.json を読み込んで AccountConfig を返す。"""
    path = os.path.join(_ACCOUNTS_DIR, f"{account_id}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"アカウント設定ファイルが見つかりません: {path}\n"
            f"config/accounts/{account_id}.json を作成してください。"
        )

    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    if cfg.get("account_id", account_id) != account_id:
        raise ValueError(
            f"設定ファイルの account_id ({cfg.get('account_id')}) が "
            f"ファイル名 ({account_id}) と一致しません"
        )

    forbidden_kw, forbidden_th = _merge_seeds_forbidden(account_id, cfg)

    return AccountConfig(
        account_id=account_id,
        display_name=cfg.get("display_name", account_id),
        status=cfg.get("status", "draft_only"),
        platforms=cfg.get("platforms", ["x", "threads"]),
        persona=cfg.get("persona", ""),
        target_audience=cfg.get("target_audience", ""),
        primary_goal=cfg.get("primary_goal", ""),
        secondary_goals=cfg.get("secondary_goals", []),
        tone=cfg.get("tone", ""),
        first_person=cfg.get("first_person", "私"),
        content_categories=cfg.get("content_categories", []),
        forbidden_themes=forbidden_th,
        forbidden_keywords=forbidden_kw,
        platform_policy=cfg.get("platform_policy", {}),
        cta_policy=cfg.get("cta_policy", {}),
        reference_source_policy=cfg.get("reference_source_policy", {}),
        video_policy=cfg.get("video_policy", {}),
        thread_series_policy=cfg.get("thread_series_policy", {}),
        learning_policy=cfg.get("learning_policy", {}),
        safety_policy=cfg.get("safety_policy", {}),
    )


def get_all_account_ids() -> list[str]:
    """config/accounts/ 以下の全アカウントIDを返す。"""
    if not os.path.isdir(_ACCOUNTS_DIR):
        return []
    return [
        f[:-5]
        for f in sorted(os.listdir(_ACCOUNTS_DIR))
        if f.endswith(".json") and not f.startswith("_")
    ]


def is_draft_only(account_id: str) -> bool:
    """アカウントが draft_only ステータスかどうかを確認する。"""
    try:
        cfg = load_account_config(account_id)
        return cfg.is_draft_only()
    except FileNotFoundError:
        return False


def is_active(account_id: str) -> bool:
    """アカウントが active ステータスかどうかを確認する。"""
    try:
        cfg = load_account_config(account_id)
        return cfg.is_active()
    except FileNotFoundError:
        return False


def invalidate_cache() -> None:
    """キャッシュをクリアする（テスト用）。"""
    load_account_config.cache_clear()
