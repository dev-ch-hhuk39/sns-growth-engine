"""Select a reader-facing generation context without mutating learning rules."""
from __future__ import annotations

from collections import Counter
from typing import Any


DEFAULT_THEMES = {
    "night_scout": ("shop_selection", "work_conditions", "transfer_and_fit", "future_options", "customer_fit"),
    "liver_manager": ("beginner_anxiety", "first_viewer_experience", "consistent_streaming", "viewer_participation", "sustainable_growth"),
}


def _metric_score(row: dict[str, Any]) -> float:
    if str(row.get("metrics_status", "")).upper() != "MEASURED":
        return 0.0
    views = float(row.get("views") or 0)
    likes = float(row.get("likes") or 0)
    comments = float(row.get("comments") or 0)
    return (likes + comments * 2) / max(views, 1)


def select_generation_context(
    *,
    account_id: str,
    posted_results: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    category_scores: list[dict[str, Any]],
    learning_rules: list[dict[str, Any]],
    requested_theme: str = "",
) -> dict[str, Any]:
    """Return a safe, explainable input context for original/reference generation."""
    recent = [row for row in posted_results if str(row.get("account_id", "")) == account_id][-20:]
    used_themes = [str(row.get("theme") or row.get("category") or "").strip() for row in recent]
    use_counts = Counter(theme for theme in used_themes if theme)
    themes = DEFAULT_THEMES.get(account_id, ())
    candidates = [requested_theme] if requested_theme else list(themes)
    selected_theme = min(candidates, key=lambda theme: (use_counts.get(theme, 0), list(themes).index(theme) if theme in themes else 999)) if candidates else "reader_guidance"
    scores = [row for row in category_scores if str(row.get("account_id", "")) == account_id]
    ranked_categories = sorted(scores, key=lambda row: float(row.get("total_score") or 0), reverse=True)[:3]
    measured = [row for row in metric_rows if str(row.get("account_id", "")) == account_id and str(row.get("metrics_status", "")).upper() == "MEASURED"]
    safe_rules = [row for row in learning_rules if str(row.get("account_id", "")) == account_id and str(row.get("status", "")).upper() in {"WAITING_REVIEW", "APPROVED"} and str(row.get("active", "")).lower() != "true"]
    return {
        "account_id": account_id,
        "selected_theme": selected_theme,
        "recent_theme_counts": dict(use_counts),
        "recent_post_count": len(recent),
        "avoid_recent_texts": [str(row.get("posted_text", ""))[:160] for row in recent[-10:]],
        "measured_post_count": len(measured),
        "best_measured_engagement_rate": max((_metric_score(row) for row in measured), default=0.0),
        "category_evidence": [{"category": row.get("category_name", ""), "score": row.get("total_score", "")} for row in ranked_categories],
        "learning_rule_candidates": [str(row.get("rule_id") or row.get("suggestion_id") or "") for row in safe_rules[:5]],
        "learning_rules_auto_applied": False,
    }
