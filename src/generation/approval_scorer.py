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

from seeds import ACCOUNT_FORBIDDEN_KEYWORDS, ACCOUNT_FORBIDDEN_THEMES
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
# コンテンツテーマガード（Phase 2.17）
# ------------------------------------------------------------------ #

def detect_forbidden_keywords(text: str, forbidden_keywords: list[str]) -> list[str]:
    """本文中の禁止キーワードを検出する。ヒットしたキーワードリストを返す。"""
    if not text or not forbidden_keywords:
        return []
    return [kw for kw in forbidden_keywords if kw in text]


def calculate_target_fit_score(draft: dict, account_config: dict) -> float:
    """ターゲット適合スコアを計算する（0.0〜1.0）。forbidden_hits数に応じて減点。"""
    account_id = str(account_config.get("account_id", ""))
    forbidden = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
    text = str(draft.get("body_md") or draft.get("content") or "")
    cta = str(draft.get("cta_text") or "")
    combined = text + " " + cta

    hits = detect_forbidden_keywords(combined, forbidden)
    if not hits:
        return 1.0
    penalty = min(1.0, len(hits) * 0.3)
    return max(0.0, 1.0 - penalty)


def check_content_theme(draft: dict, account_config: dict) -> dict[str, Any]:
    """アカウントのターゲットテーマチェック。

    Returns:
        {
            "theme_ok": bool,
            "forbidden_hits": list[str],
            "target_fit_score": float,
            "theme_rejection_reason": str,
        }
    """
    account_id = str(account_config.get("account_id", ""))
    forbidden = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])

    text = str(draft.get("body_md") or draft.get("content") or "")
    cta = str(draft.get("cta_text") or "")
    combined = text + " " + cta

    hits = detect_forbidden_keywords(combined, forbidden)
    target_fit = calculate_target_fit_score(draft, account_config)
    theme_ok = len(hits) == 0

    reason = ""
    if hits:
        reason = f"禁止キーワードを検出: {hits}"

    return {
        "theme_ok": theme_ok,
        "forbidden_hits": hits,
        "target_fit_score": round(target_fit, 4),
        "theme_rejection_reason": reason,
    }


def apply_content_theme_guard(
    score_result: dict,
    draft: dict,
    account_config: dict,
) -> dict:
    """content_theme_check の結果を score_result に適用する。

    forbidden_hits > 0 の場合:
      - ai_publish_recommendation = "reject"
      - confidence_level = "LOW"
      - brand_risk_score を上昇させる
      - ai_review に target_mismatch 理由を追記
    """
    theme = check_content_theme(draft, account_config)
    score_result["target_fit_score"] = theme["target_fit_score"]
    score_result["theme_rejection_reason"] = theme["theme_rejection_reason"]

    if not theme["theme_ok"]:
        score_result["ai_publish_recommendation"] = "reject"
        score_result["confidence_level"] = "LOW"
        score_result["brand_risk_score"] = min(
            1.0,
            float(score_result.get("brand_risk_score") or 0.0) + 0.4,
        )
        existing_review = str(score_result.get("ai_review") or "")
        guard_note = f"[content_theme_guard] target_mismatch: {theme['theme_rejection_reason']}"
        score_result["ai_review"] = (existing_review + " / " + guard_note).strip(" /")

    return score_result


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
    account_config: dict | None = None,
) -> dict[str, Any]:
    """生成投稿に対して総合スコアリングを行う。

    Args:
        draft: drafts タブの1行データ
        reference_score: reference_post_scores レコード（任意）
        reference_post: reference_posts レコード（任意）
        media_asset: media_assets レコード（任意）
        auto_approve_threshold: 自動承認スコア閾値
        platform: プラットフォーム（"x" / "threads"）
        account_config: アカウント設定dict（コンテンツテーマガード用）

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

    result = {
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

    # Phase 2.17: コンテンツテーマガード
    if account_config:
        result = apply_content_theme_guard(result, draft, account_config)
        if result.get("ai_publish_recommendation") == "reject":
            result["suggested_status"] = "WAITING_REVIEW"

    return result


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
