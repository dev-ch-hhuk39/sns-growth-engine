"""Evidence-based post attribution and bounded generation strategy updates.

This module does not claim causal certainty. It compares posts at the same
measurement window and explains which recorded generation features are
associated with above- or below-baseline outcomes. Strategy updates remain
bounded, preserve exploration, and never rewrite prompts or code.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

FEATURE_SCHEMA_VERSION = "post_features_v1"
ATTRIBUTION_VERSION = "growth_attribution_v1"
STRATEGY_VERSION = "bounded_strategy_v1"
STRATEGY_DIMENSIONS = (
    "primary_topic",
    "structure_variant",
    "cta_intent",
    "content_route",
    "generation_mode",
    "content_type",
    "media_format",
)
PREFERRED_WINDOWS = (168, 72, 24)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    text = _text(value)
    if text == "":
        return None
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _int(value: Any, default: int = 0) -> int:
    number = _number(value)
    return int(number) if number is not None else default


def _window_hours(row: dict[str, Any]) -> int:
    for key in ("collection_window_hours", "window_hours", "measurement_window"):
        value = _text(row.get(key))
        if not value:
            continue
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            return int(digits)
    return 0


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes"}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(_text(value) or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _percentile(values: list[float], value: float) -> float:
    if len(values) <= 1:
        return 0.5
    below = sum(1 for item in values if item < value)
    equal = sum(1 for item in values if item == value)
    return round((below + max(0, equal - 1) / 2) / (len(values) - 1), 4)


def _feature_value(
    row: dict[str, Any],
    dimension: str,
) -> str:
    if dimension == "content_route":
        return _text(
            row.get("content_route")
            or row.get("content_type")
            or row.get("generation_mode")
            or "unknown"
        )

    if dimension == "generation_mode":
        return _text(
            row.get("generation_mode")
            or row.get("content_type")
            or "unknown"
        )

    if dimension == "content_type":
        return _text(
            row.get("content_type")
            or row.get("generation_mode")
            or "unknown"
        )

    if dimension == "media_format":
        if _bool(row.get("media_used")):
            return _text(
                row.get("publisher_media_type")
                or row.get("media_type")
                or row.get("content_type")
                or "media"
            )

        return "text_only"

    return _text(
        row.get(dimension) or "unknown"
    )


def _metric_payload(row: dict[str, Any]) -> dict[str, float | None]:
    views = _number(row.get("views") or row.get("impressions"))
    likes = _number(row.get("likes"))
    comments = _number(row.get("comments") or row.get("replies"))
    reposts = _number(row.get("reposts") or row.get("shares"))
    follows = _number(row.get("follows"))
    engagement_values = [value for value in (likes, comments, reposts) if value is not None]
    engagement = sum(engagement_values) if engagement_values else None
    engagement_rate = engagement / views if engagement is not None and views and views > 0 else None
    follow_rate = follows / views if follows is not None and views and views > 0 else None
    return {
        "views": views,
        "likes": likes,
        "comments": comments,
        "reposts": reposts,
        "follows": follows,
        "engagement_rate": engagement_rate,
        "follow_rate": follow_rate,
    }


def build_observations(
    posted_results: Iterable[dict[str, Any]],
    metric_snapshots: Iterable[dict[str, Any]],
    *,
    account_id: str = "all",
) -> list[dict[str, Any]]:
    """Join post features to the best available measured window per result."""
    posts = {
        _text(row.get("result_id")): dict(row)
        for row in posted_results
        if _text(row.get("result_id"))
        and (account_id == "all" or _text(row.get("account_id")) == account_id)
        and _text(row.get("status")).upper() in {"POSTED", "RECOVERED", ""}
        and _text(row.get("feature_schema_version")) == FEATURE_SCHEMA_VERSION
    }
    snapshots_by_result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in metric_snapshots:
        result_id = _text(row.get("result_id"))
        if result_id not in posts:
            continue
        metrics = _metric_payload(row)
        if not any(value is not None for key, value in metrics.items() if key in {"views", "likes", "comments", "reposts", "follows"}):
            continue
        snapshots_by_result[result_id].append(dict(row))

    observations: list[dict[str, Any]] = []
    for result_id, post in posts.items():
        snapshots = snapshots_by_result.get(result_id, [])
        selected: dict[str, Any] | None = None
        if snapshots:
            def priority(row: dict[str, Any]) -> tuple[int, str]:
                window = _window_hours(row)
                preferred = len(PREFERRED_WINDOWS) - PREFERRED_WINDOWS.index(window) if window in PREFERRED_WINDOWS else 0
                return preferred, _text(row.get("collected_at"))
            selected = max(snapshots, key=priority)
        elif _text(post.get("metrics_status")).upper() == "MEASURED":
            selected = post
        if selected is None:
            continue
        window = _window_hours(selected) or _window_hours(post)
        metrics = _metric_payload(selected)
        if metrics["views"] is None and metrics["engagement_rate"] is None:
            continue
        features = {dimension: _feature_value(post, dimension) for dimension in STRATEGY_DIMENSIONS}
        observations.append({
            "result_id": result_id,
            "queue_id": _text(post.get("queue_id")),
            "canary_id": _text(post.get("canary_id")),
            "account_id": _text(post.get("account_id")),
            "platform": _text(post.get("platform") or "threads"),
            "window_hours": window,
            "posted_at": _text(post.get("posted_at")),
            "collected_at": _text(selected.get("collected_at")),
            "metrics_status": _text(selected.get("metrics_status") or selected.get("collection_status") or post.get("metrics_status")),
            "features": features,
            "metrics": metrics,
            "feature_schema_version": _text(post.get("feature_schema_version")),
        })
    return observations


def _score_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in observations:
        grouped[(item["account_id"], int(item["window_hours"]))].append(item)

    scored: list[dict[str, Any]] = []
    for (_, _), rows in grouped.items():
        views_values = [float(row["metrics"]["views"]) for row in rows if row["metrics"]["views"] is not None]
        er_values = [float(row["metrics"]["engagement_rate"]) for row in rows if row["metrics"]["engagement_rate"] is not None]
        follow_values = [float(row["metrics"]["follow_rate"]) for row in rows if row["metrics"]["follow_rate"] is not None]
        row_scores: list[float] = []
        for row in rows:
            components: list[tuple[float, float]] = []
            metrics = row["metrics"]
            if metrics["views"] is not None:
                components.append((0.55, _percentile(views_values, float(metrics["views"]))))
            if metrics["engagement_rate"] is not None:
                components.append((0.35, _percentile(er_values, float(metrics["engagement_rate"]))))
            if metrics["follow_rate"] is not None:
                components.append((0.10, _percentile(follow_values, float(metrics["follow_rate"]))))
            weight_sum = sum(weight for weight, _ in components)
            score = sum(weight * value for weight, value in components) / weight_sum if weight_sum else 0.5
            score = round(score, 4)
            row_scores.append(score)
            scored.append({**row, "performance_score": score, "metric_component_count": len(components), "comparison_group_size": len(rows)})
        baseline = statistics.median(row_scores) if row_scores else 0.5
        for item in scored[-len(rows):]:
            item["account_baseline_score"] = round(baseline, 4)
            item["delta_vs_baseline"] = round(item["performance_score"] - baseline, 4)
    return scored


def _feature_statistics(scored: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    values: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in scored:
        for dimension, feature_value in item["features"].items():
            values[(item["account_id"], dimension, feature_value)].append(item)
    stats: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, rows in values.items():
        scores = [float(row["performance_score"]) for row in rows]
        stats[key] = {
            "sample_count": len(rows),
            "mean_score": round(sum(scores) / len(scores), 4),
            "result_ids": [row["result_id"] for row in rows],
        }
    return stats


def _confidence(*, comparison_group_size: int, metric_component_count: int, feature_sample_count: int) -> float:
    sample_factor = min(1.0, comparison_group_size / 10)
    feature_factor = min(1.0, feature_sample_count / 6)
    metric_factor = min(1.0, metric_component_count / 3)
    return round(0.45 * sample_factor + 0.35 * feature_factor + 0.20 * metric_factor, 4)


def build_attributions(observations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scored = _score_observations(observations)
    feature_stats = _feature_statistics(scored)
    account_means: dict[str, float] = {}
    for account in {item["account_id"] for item in scored}:
        values = [float(item["performance_score"]) for item in scored if item["account_id"] == account]
        account_means[account] = sum(values) / len(values) if values else 0.5

    attributions: list[dict[str, Any]] = []
    for item in scored:
        reasons: list[str] = []
        evidence: list[dict[str, Any]] = []
        confidence_values: list[float] = []
        for dimension, value in item["features"].items():
            stat = feature_stats[(item["account_id"], dimension, value)]
            delta = round(float(stat["mean_score"]) - account_means[item["account_id"]], 4)
            confidence = _confidence(
                comparison_group_size=int(item["comparison_group_size"]),
                metric_component_count=int(item["metric_component_count"]),
                feature_sample_count=int(stat["sample_count"]),
            )
            confidence_values.append(confidence)
            direction = "POSITIVE" if delta >= 0.05 else "NEGATIVE" if delta <= -0.05 else "NEUTRAL"
            if stat["sample_count"] >= 2 and direction != "NEUTRAL":
                reasons.append(f"{dimension.upper()}_{direction}_ASSOCIATION")
            evidence.append({
                "dimension": dimension,
                "value": value,
                "sample_count": stat["sample_count"],
                "mean_performance_score": stat["mean_score"],
                "delta_vs_account": delta,
                "direction": direction,
                "confidence": confidence,
            })
        delta = float(item["delta_vs_baseline"])
        if int(item["comparison_group_size"]) < 3:
            outcome = "INSUFFICIENT_COMPARISON_DATA"
            reasons.insert(0, "COMPARISON_SAMPLE_BELOW_3")
        elif delta >= 0.10:
            outcome = "OUTPERFORMED"
            reasons.insert(0, "ABOVE_ACCOUNT_WINDOW_BASELINE")
        elif delta <= -0.10:
            outcome = "UNDERPERFORMED"
            reasons.insert(0, "BELOW_ACCOUNT_WINDOW_BASELINE")
        else:
            outcome = "NEUTRAL"
            reasons.insert(0, "WITHIN_ACCOUNT_WINDOW_BASELINE")
        if not any(reason.endswith("ASSOCIATION") for reason in reasons):
            reasons.append("FEATURE_EFFECT_NOT_YET_DISTINGUISHABLE")
        overall_confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0.0
        positive = [f"{row['dimension']}={row['value']}" for row in evidence if row["direction"] == "POSITIVE" and row["sample_count"] >= 2]
        negative = [f"{row['dimension']}={row['value']}" for row in evidence if row["direction"] == "NEGATIVE" and row["sample_count"] >= 2]
        explanation_parts = [
            f"同一{item['window_hours']}時間窓のアカウント基準比は{delta:+.3f}。",
            "これは因果断定ではなく、記録済み特徴との関連評価です。",
        ]
        if positive:
            explanation_parts.append("上振れ関連: " + "、".join(positive[:3]) + "。")
        if negative:
            explanation_parts.append("下振れ関連: " + "、".join(negative[:3]) + "。")
        if int(item["comparison_group_size"]) < 3:
            explanation_parts.append("比較投稿数が3件未満のため、現段階では学習配分を変更しません。")
        attribution_id = f"attr_{item['result_id']}_{item['window_hours']}"
        attributions.append({
            "attribution_id": attribution_id,
            "attribution_version": ATTRIBUTION_VERSION,
            "result_id": item["result_id"],
            "queue_id": item["queue_id"],
            "canary_id": item["canary_id"],
            "account_id": item["account_id"],
            "platform": item["platform"],
            "window_hours": item["window_hours"],
            "metrics_status": item["metrics_status"],
            "performance_score": item["performance_score"],
            "account_baseline_score": item["account_baseline_score"],
            "delta_vs_baseline": item["delta_vs_baseline"],
            "outcome_label": outcome,
            "confidence": overall_confidence,
            "reason_codes_json": json.dumps(reasons, ensure_ascii=False),
            "explanation": " ".join(explanation_parts),
            "feature_evidence_json": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
            "metric_evidence_json": json.dumps(item["metrics"], ensure_ascii=False, sort_keys=True),
            "created_at": _now(),
        })

    strategy_rows: list[dict[str, Any]] = []
    for (account, dimension, value), stat in sorted(feature_stats.items()):
        account_rows = [item for item in scored if item["account_id"] == account]
        account_count = len(account_rows)
        delta = round(float(stat["mean_score"]) - account_means[account], 4)
        confidence = _confidence(
            comparison_group_size=account_count,
            metric_component_count=3,
            feature_sample_count=int(stat["sample_count"]),
        )
        eligible = account_count >= 8 and int(stat["sample_count"]) >= 3 and confidence >= 0.45
        raw_weight = max(0.5, min(1.5, 1.0 + delta * 1.5)) if eligible else 1.0
        stable = hashlib.sha256(f"{account}|{dimension}|{value}".encode()).hexdigest()[:16]
        strategy_rows.append({
            "strategy_id": f"strategy_{stable}",
            "strategy_version": STRATEGY_VERSION,
            "account_id": account,
            "dimension": dimension,
            "feature_value": value,
            "sample_count": stat["sample_count"],
            "account_sample_count": account_count,
            "mean_performance_score": stat["mean_score"],
            "delta_vs_account": delta,
            "confidence": confidence,
            "allocation_weight": round(raw_weight, 4),
            "exploration_floor": 0.20,
            "status": "ACTIVE" if eligible else "OBSERVE",
            "evidence_result_ids_json": json.dumps(stat["result_ids"], ensure_ascii=False),
            "updated_at": _now(),
        })

    # Normalize active allocation weights within each account/dimension while
    # retaining an exploration floor. OBSERVE rows remain neutral at 1.0.
    grouped_strategy: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in strategy_rows:
        grouped_strategy[(row["account_id"], row["dimension"])].append(row)
    for rows in grouped_strategy.values():
        active = [row for row in rows if row["status"] == "ACTIVE"]
        if not active:
            continue
        total = sum(float(row["allocation_weight"]) for row in active) or 1.0
        for row in active:
            normalized = float(row["allocation_weight"]) / total
            row["allocation_weight"] = round(max(float(row["exploration_floor"]) / len(active), normalized), 4)
    return attributions, strategy_rows


def preferred_primary_topics(strategy_rows: Iterable[dict[str, Any]], account_id: str, *, limit: int = 2) -> list[str]:
    eligible = [
        row for row in strategy_rows
        if _text(row.get("account_id")) == account_id
        and _text(row.get("dimension")) == "primary_topic"
        and _text(row.get("status")).upper() == "ACTIVE"
        and _text(row.get("feature_value")) not in {"", "unknown", "general"}
    ]
    eligible.sort(key=lambda row: (float(row.get("allocation_weight") or 0), float(row.get("confidence") or 0)), reverse=True)
    return [_text(row.get("feature_value")) for row in eligible[:limit]]


def build_growth_cycle(
    posted_results: list[dict[str, Any]],
    metric_snapshots: list[dict[str, Any]],
    *,
    account_id: str = "all",
) -> dict[str, Any]:
    observations = build_observations(posted_results, metric_snapshots, account_id=account_id)
    attributions, strategy_rows = build_attributions(observations)
    return {
        "status": "PLAN_ONLY",
        "attribution_version": ATTRIBUTION_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "account_id": account_id,
        "observation_count": len(observations),
        "attribution_count": len(attributions),
        "strategy_row_count": len(strategy_rows),
        "active_strategy_count": sum(1 for row in strategy_rows if row["status"] == "ACTIVE"),
        "attributions": attributions,
        "strategy_state": strategy_rows,
        "safety": {
            "causal_claims": False,
            "prompt_or_code_rewrite": False,
            "bounded_allocation_updates": True,
            "exploration_floor": 0.20,
            "minimum_account_samples_for_activation": 8,
            "minimum_feature_samples_for_activation": 3,
        },
    }
