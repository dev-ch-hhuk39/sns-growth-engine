"""
approval_scorer.py — AI承認スコアリング（Phase 2.15）

生成された投稿文（drafts）に対して複数の観点でスコアリングを行い、
自動承認可否を判定する。

publish_decision.py（既存）との役割分担:
  - approval_scorer.py（本モジュール）: 生成時点のAIスコアリング
  - publish_decision.py（既存）: 承認済み下書きのキューイング判定
"""
from __future__ import annotations

from typing import Any

from text_policy import check_text_policy

_BUZZ_SCORE_WEIGHTS = {
    "hook_style_bonus": 10.0,
    "cta_bonus": 5.0,
    "ok_policy_bonus": 10.0,
    "warn_policy_penalty": 5.0,
    "fail_policy_penalty": 20.0,
}

_VALID_IMITATION_RISKS = {"low", "medium", "high", "unknown"}
_VALID_MEDIA_REUSE_RISKS = {"low", "medium", "high", "unknown"}


# ------------------------------------------------------------------ #
# 個別スコア計算
# ------------------------------------------------------------------ #

def calculate_buzz_potential_score(
    draft: dict,
    reference_score: dict | None = None,
) -> float:
    """バズ可能性スコアを計算する（0〜100）。

    参考投稿の buzz_score をベースに、フック有無・文字数・CTA等で補正する。
    """
    base = 0.0
    if reference_score:
        base = min(100.0, float(reference_score.get("buzz_score") or 0) * 0.7)

    content = str(draft.get("body_md") or draft.get("content") or "")
    platform = str(draft.get("platform", "x")).lower()

    policy = check_text_policy(content, platform) if content and platform in ("x", "threads") else None

    bonus = 0.0
    if str(draft.get("generation_mode", "")) == "reference_based":
        bonus += _BUZZ_SCORE_WEIGHTS["hook_style_bonus"]
    if str(draft.get("cta_text", "")).strip():
        bonus += _BUZZ_SCORE_WEIGHTS["cta_bonus"]
    if policy:
        if policy.status == "OK":
            bonus += _BUZZ_SCORE_WEIGHTS["ok_policy_bonus"]
        elif policy.status == "WARN":
            bonus -= _BUZZ_SCORE_WEIGHTS["warn_policy_penalty"]
        elif policy.status == "FAIL":
            bonus -= _BUZZ_SCORE_WEIGHTS["fail_policy_penalty"]

    return min(100.0, max(0.0, base + bonus))


def calculate_conversion_potential_score(draft: dict) -> float:
    """コンバージョン可能性スコアを計算する（0〜100）。

    CTA有無・プロフィール誘導文・LINE誘導テキストの有無をチェックする。
    """
    content = str(draft.get("body_md") or draft.get("content") or "").lower()
    cta = str(draft.get("cta_text", "")).strip()

    score = 30.0  # ベース
    if cta:
        score += 25.0
    if any(kw in content for kw in ("line", "ライン", "相談", "dm", "プロフィール")):
        score += 20.0
    if any(kw in content for kw in ("無料", "今すぐ", "限定", "期間", "キャンペーン")):
        score += 15.0
    if any(kw in content for kw in ("→", "▼", "↓", "【", "■")):
        score += 10.0

    return min(100.0, score)


def calculate_brand_risk_score(
    draft: dict,
    reference_post: dict | None = None,
) -> float:
    """ブランドリスクスコアを計算する（0.0〜1.0、低いほど安全）。"""
    risk = 0.0

    imitation = str(
        draft.get("imitation_risk")
        or (reference_post.get("imitation_risk") if reference_post else None)
        or "unknown"
    ).lower()

    if imitation == "high":
        risk += 0.4
    elif imitation == "medium":
        risk += 0.2
    elif imitation == "low":
        risk += 0.05

    content = str(draft.get("body_md") or draft.get("content") or "")
    ref_text = str(reference_post.get("text") or reference_post.get("original_text") or "") if reference_post else ""

    if content and ref_text:
        overlap = _text_overlap_ratio(content, ref_text)
        risk += min(0.4, overlap * 0.6)

    return min(1.0, risk)


def calculate_imitation_risk(draft: dict, reference_post: dict | None = None) -> str:
    """模倣リスクを返す: low / medium / high / unknown。"""
    direct = str(draft.get("imitation_risk", "")).lower()
    if direct in _VALID_IMITATION_RISKS:
        return direct
    if reference_post:
        ref_risk = str(reference_post.get("imitation_risk", "")).lower()
        if ref_risk in _VALID_IMITATION_RISKS:
            return ref_risk
    return "unknown"


def calculate_media_reuse_risk(
    draft: dict,
    media_asset: dict | None = None,
) -> str:
    """メディア再利用リスクを返す: low / medium / high / unknown。"""
    direct = str(draft.get("media_reuse_risk", "")).lower()
    if direct in _VALID_MEDIA_REUSE_RISKS:
        return direct
    if media_asset:
        asset_risk = str(media_asset.get("media_reuse_risk", "")).lower()
        if asset_risk in _VALID_MEDIA_REUSE_RISKS:
            return asset_risk
    return "unknown"


# ------------------------------------------------------------------ #
# 総合判定
# ------------------------------------------------------------------ #

def calculate_confidence_level(
    buzz_potential_score: float,
    brand_risk_score: float,
    text_policy_status: str,
) -> str:
    """総合信頼度を返す: HIGH / MEDIUM / LOW。"""
    if (buzz_potential_score >= 70.0
            and brand_risk_score <= 0.3
            and str(text_policy_status).upper() == "OK"):
        return "HIGH"
    if buzz_potential_score >= 50.0 and brand_risk_score <= 0.5:
        return "MEDIUM"
    return "LOW"


def should_auto_approve(
    buzz_potential_score: float,
    auto_approve_threshold: float,
) -> bool:
    """buzz_potential_score が閾値以上なら自動承認する。"""
    return buzz_potential_score >= auto_approve_threshold


def calculate_ai_publish_recommendation(
    confidence_level: str,
    imitation_risk: str,
    brand_risk_score: float,
) -> str:
    """AIによる投稿推奨を返す: recommend / review / reject。"""
    cl = str(confidence_level).upper()
    ir = str(imitation_risk).lower()

    if brand_risk_score > 0.7 or cl == "LOW":
        return "reject"
    if cl == "HIGH" and ir != "high":
        return "recommend"
    return "review"


# ------------------------------------------------------------------ #
# メインスコアリング
# ------------------------------------------------------------------ #

def score_generated_post(
    draft: dict,
    reference_score: dict | None = None,
    reference_post: dict | None = None,
    media_asset: dict | None = None,
    auto_approve_threshold: float = 80.0,
    platform: str | None = None,
) -> dict[str, Any]:
    """生成投稿に対して総合スコアリングを行う。

    Args:
        draft: drafts タブの1行データ
        reference_score: reference_post_scores レコード（任意）
        reference_post: reference_posts レコード（任意）
        media_asset: media_assets レコード（任意）
        auto_approve_threshold: 自動承認スコア閾値
        platform: プラットフォーム（"x" / "threads"）

    Returns:
        スコア結果dict（drafts タブ更新用フィールドを含む）
    """
    if platform is None:
        platform = str(draft.get("platform", "x")).lower()

    content = str(draft.get("body_md") or draft.get("content") or "")
    draft_with_platform = {**draft, "platform": platform}

    policy_result = check_text_policy(content, platform) if content and platform in ("x", "threads") else None
    text_policy_status = policy_result.status if policy_result else "OK"

    buzz = calculate_buzz_potential_score(draft_with_platform, reference_score)
    conversion = calculate_conversion_potential_score(draft)
    brand_risk = calculate_brand_risk_score(draft, reference_post)
    imitation_risk = calculate_imitation_risk(draft, reference_post)
    media_reuse = calculate_media_reuse_risk(draft, media_asset)
    confidence = calculate_confidence_level(buzz, brand_risk, text_policy_status)
    recommendation = calculate_ai_publish_recommendation(confidence, imitation_risk, brand_risk)
    auto_approve = should_auto_approve(buzz, auto_approve_threshold)

    final_status = "APPROVED" if auto_approve else "WAITING_REVIEW"
    if text_policy_status == "FAIL":
        final_status = "WAITING_REVIEW"

    return {
        "buzz_potential_score": round(buzz, 2),
        "conversion_potential_score": round(conversion, 2),
        "brand_risk_score": round(brand_risk, 4),
        "imitation_risk": imitation_risk,
        "media_reuse_risk": media_reuse,
        "text_policy_status": text_policy_status,
        "confidence_level": confidence,
        "ai_publish_recommendation": recommendation,
        "suggested_status": final_status,
    }


# ------------------------------------------------------------------ #
# ユーティリティ
# ------------------------------------------------------------------ #

def _text_overlap_ratio(text_a: str, text_b: str) -> float:
    """2テキスト間の文字レベル重複率を返す（0.0〜1.0）。

    Jaccard 係数の文字bigram版。
    """
    if not text_a or not text_b:
        return 0.0

    def bigrams(s: str) -> set[str]:
        return {s[i:i + 2] for i in range(len(s) - 1)}

    ba, bb = bigrams(text_a), bigrams(text_b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)
