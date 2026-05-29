"""
publish_decision.py - 投稿可否判定ロジック（純粋関数）

外部依存なし。すべてステートレスな純粋関数として実装する。
DRY_RUN 制御は呼び出し元で行う。
"""
from __future__ import annotations


def _safe_float(value: object, default: float) -> float:
    """型・値に依らず安全に float へ変換する。"""
    try:
        return float(value) if value not in ("", None) else default
    except (ValueError, TypeError):
        return default


def decide_draft_status(draft: dict, account: dict) -> str:
    """下書きの公開ステータスを判定する。

    Returns: READY | HUMAN_REVIEW | DRAFT | REJECT
      - REJECT        : Gemini が明示的に REJECT と評価（呼び出し元が設定した場合）
      - HUMAN_REVIEW  : brand_risk_score が閾値超過
      - DRAFT         : スコアが min_publish_score 未満
      - READY         : すべての条件をパス
    """
    score = _safe_float(draft.get("score") or draft.get("pv_score"), 0)
    cv_score = _safe_float(draft.get("cv_score"), 0)
    brand_risk = _safe_float(draft.get("brand_risk_score"), 100)

    min_score = _safe_float(account.get("min_publish_score"), 65)
    risk_threshold = _safe_float(account.get("brand_risk_threshold"), 25)

    # score と cv_score の両方がある場合は平均を使う
    combined = (score + cv_score) / 2 if cv_score > 0 else score

    if brand_risk > risk_threshold:
        return "HUMAN_REVIEW"
    if combined < min_score:
        return "DRAFT"
    return "READY"


def decide_derivative_status(derivative: dict, draft: dict, account: dict) -> str:
    """social_derivative のステータスを判定する。

    Returns: READY | HUMAN_REVIEW | REJECT
      - Gemini が REJECT と判定した場合はそのまま採用
      - draft の brand_risk_score が閾値超過なら HUMAN_REVIEW
      - それ以外は READY（queue 側で auto_publish を見て WAITING_REVIEW に変換）
    """
    gemini_status = str(derivative.get("status", "")).upper()
    if gemini_status == "REJECT":
        return "REJECT"

    brand_risk = _safe_float(draft.get("brand_risk_score"), 100)
    risk_threshold = _safe_float(account.get("brand_risk_threshold"), 25)

    if brand_risk > risk_threshold:
        return "HUMAN_REVIEW"

    return "READY"


def should_queue(
    derivative: dict, draft: dict, account: dict
) -> tuple[bool, str, str]:
    """キューに積むべきかを判定する。

    Returns:
      (should_add: bool, queue_status: str, reason: str)

    queue_status の意味:
      READY          : 自動投稿可（auto_publish=TRUE かつ全条件パス）
      WAITING_REVIEW : キューには積むが手動確認待ち
      REJECTED       : キューに積まない
    """
    d_status = str(derivative.get("status", "")).upper()

    if d_status == "REJECT":
        return False, "REJECTED", "derivative status=REJECT のため除外"

    if d_status == "HUMAN_REVIEW":
        return True, "WAITING_REVIEW", "HUMAN_REVIEW のため人間確認待ち"

    auto_publish = str(account.get("auto_publish", "FALSE")).strip().upper()
    if auto_publish != "TRUE":
        return True, "WAITING_REVIEW", "auto_publish=FALSE のため手動確認待ち"

    # スコアチェック
    brand_risk = _safe_float(draft.get("brand_risk_score"), 100)
    risk_threshold = _safe_float(account.get("brand_risk_threshold"), 25)
    if brand_risk > risk_threshold:
        return (
            True,
            "WAITING_REVIEW",
            f"brand_risk_score={brand_risk:.0f} > threshold={risk_threshold:.0f}",
        )

    score = _safe_float(draft.get("score") or draft.get("pv_score"), 0)
    cv_score = _safe_float(draft.get("cv_score"), 0)
    combined = (score + cv_score) / 2 if cv_score > 0 else score
    min_score = _safe_float(account.get("min_publish_score"), 65)
    if combined < min_score:
        return (
            True,
            "WAITING_REVIEW",
            f"combined_score={combined:.1f} < min_publish_score={min_score:.0f}",
        )

    return True, "READY", "全条件パス"
