"""source選定スコアリング。

回収済み共有source(default_sources.json)の優先順位評価。
方針(ユーザー共有済みルール):
- 公式/メディア系は低優先 (media_official_penalty)
- 個人インフルエンサー/ノウハウ発信者/伸びている配信者を高優先
- platform優先度: TikTok > Threads/X > YouTube
- night_scout / liver_manager との適合度を重視
- third-party media reuse リスクが高いものは REFERENCE_ONLY 前提

注意: ここでの score は「参考収集/採点の並び替え・候補提示」用であり、
priority の自動変更や実投稿判定には用いない (auto_priority_change_allowed=false)。
"""
from __future__ import annotations

import re
from typing import Any

_MEDIA_OFFICIAL_PAT = re.compile(
    r"(official|公式|news|magazine|prtimes|television|press|broadcast|oricon|"
    r"nikkei|asahi|mainichi|yomiuri|sankei|nhk|low_priority_media_official)",
    re.IGNORECASE,
)
_PERSONAL_PAT = re.compile(
    r"(personal|individual|influencer|creator|streamer|配信者|個人|キャバ|scout|liver|ライバー)",
    re.IGNORECASE,
)
_KNOWHOW_PAT = re.compile(
    r"(knowhow|know_how|ノウハウ|tips|攻略|解説|how_?to|growth|戦略|稼ぎ方|集客)",
    re.IGNORECASE,
)

_PLATFORM_PRIORITY = {
    "tiktok": 1.0,
    "threads": 0.8,
    "x": 0.8,
    "instagram": 0.6,
    "note": 0.5,
    "youtube": 0.45,
    "manual_url": 0.4,
    "query": 0.3,
}

_CATEGORY_FIT = {
    "night_scout": {
        "night_work_scout", "cabaret_knowhow", "night_work_women",
        "beauty_nightlife", "tiktok_live_side_income",
    },
    "liver_manager": {
        "tiktok_live_creator", "live_streaming_knowhow", "creator_growth",
        "streamer_interview", "gift_strategy",
    },
    "beauty_future": {
        "beauty_influencer", "beauty_knowhow", "cosmetic", "cosmetic_surgery",
        "glowup", "tiktok_shop_future",
    },
    "beauty_account": {
        "beauty_influencer", "beauty_knowhow", "cosmetic", "cosmetic_surgery",
        "glowup", "tiktok_shop_future", "trend_query", "video_reference", "text_reference",
    },
}


def _blob(src: dict[str, Any]) -> str:
    parts = [
        str(src.get("source_handle", "")), str(src.get("source_name", "")),
        str(src.get("source_url", "")), str(src.get("review_notes", "")),
        " ".join(src.get("use_cases", []) or []),
    ]
    cats = src.get("source_category")
    parts.extend(cats if isinstance(cats, list) else [str(cats or "")])
    parts.extend(src.get("source_categories", []) or [])
    return " ".join(parts)


def personal_creator_score(src: dict[str, Any]) -> float:
    """個人発信者らしさ。0..1。"""
    return 1.0 if _PERSONAL_PAT.search(_blob(src)) else 0.0


def knowhow_account_score(src: dict[str, Any]) -> float:
    """ノウハウ発信らしさ。0..1。"""
    return 1.0 if _KNOWHOW_PAT.search(_blob(src)) else 0.0


def media_official_penalty(src: dict[str, Any]) -> float:
    """公式/メディア系ペナルティ。0(なし)..1(該当)。"""
    return 1.0 if _MEDIA_OFFICIAL_PAT.search(_blob(src)) else 0.0


def active_recently_score(src: dict[str, Any]) -> float:
    """直近activeか(updated_at/active基準の簡易指標)。0..1。"""
    return 1.0 if src.get("active") else 0.3


def platform_priority_score(src: dict[str, Any]) -> float:
    """platform優先度。TikTok > Threads/X > YouTube。0..1。"""
    return _PLATFORM_PRIORITY.get(str(src.get("source_platform", "")), 0.3)


def category_fit_score(src: dict[str, Any]) -> float:
    """source_category と既定カテゴリ集合の適合度。0..1。"""
    cats = set()
    c = src.get("source_category")
    cats.update(c if isinstance(c, list) else [c])
    cats.update(src.get("source_categories", []) or [])
    cats.discard(None)
    fit = set()
    for s in _CATEGORY_FIT.values():
        fit |= s
    return 1.0 if cats & fit else 0.0


def target_account_fit_score(src: dict[str, Any], target: str) -> float:
    """target_account との適合度(target側カテゴリと一致するか)。0..1。"""
    if not target:
        return 0.0
    if target in {"beauty_future", "beauty_account"}:
        in_target = src.get("future_track") == "beauty_future" or "beauty_account" in (src.get("target_account_ids") or [])
    else:
        in_target = target in (src.get("target_account_ids") or [])
    if not in_target:
        return 0.0
    cats = set()
    c = src.get("source_category")
    cats.update(c if isinstance(c, list) else [c])
    cats.update(src.get("source_categories", []) or [])
    return 1.0 if cats & _CATEGORY_FIT.get(target, set()) else 0.6


def source_selection_score(src: dict[str, Any], target: str = "") -> float:
    """並び替え用の総合score。0..1目安。priority自動変更には使わない。"""
    base = (
        0.30 * personal_creator_score(src)
        + 0.20 * knowhow_account_score(src)
        + 0.20 * platform_priority_score(src)
        + 0.15 * category_fit_score(src)
        + 0.15 * (target_account_fit_score(src, target) if target else category_fit_score(src))
    )
    base += 0.05 * active_recently_score(src)
    base -= 0.35 * media_official_penalty(src)
    return round(max(0.0, min(1.0, base)), 4)
