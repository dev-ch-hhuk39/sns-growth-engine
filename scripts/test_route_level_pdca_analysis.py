#!/usr/bin/env python3
"""Verify route and generation method remain separate PDCA dimensions."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "src"),
    str(ROOT / "scripts"),
]

from learning.feature_attribution import (
    STRATEGY_DIMENSIONS,
    build_observations,
)
from learning.pdca_orchestrator import (
    PDCAOrchestrator,
)
from learning.post_result_analyzer import (
    PostResultAnalyzer,
)


results = [
    {
        "result_id": "result_original",
        "queue_id": "queue_original",
        "account_id": "liver_manager",
        "platform": "threads",
        "status": "POSTED",
        "metrics_status": "MEASURED",
        "content_type": "original_text",
        "content_route": "original_text",
        "generation_mode": "original_text",
        "feature_schema_version": (
            "post_features_v1"
        ),
        "primary_topic": "beginner_anxiety",
        "structure_variant": "1",
        "cta_intent": "education",
        "media_used": "false",
        "views": 100,
        "impressions": 100,
        "likes": 10,
        "comments": 2,
        "replies": 2,
        "reposts": 1,
        "follows": 2,
        "posted_at": "2026-08-01T01:00:00Z",
    },
    {
        "result_id": "result_pdca_fallback",
        "queue_id": "queue_pdca_fallback",
        "account_id": "liver_manager",
        "platform": "threads",
        "status": "POSTED",
        "metrics_status": "MEASURED",
        "content_type": "original_text",
        "content_route": "pdca_text",
        "generation_mode": "original_text",
        "feature_schema_version": (
            "post_features_v1"
        ),
        "primary_topic": "sustainable_growth",
        "structure_variant": "2",
        "cta_intent": "education",
        "media_used": "false",
        "views": 100,
        "impressions": 100,
        "likes": 25,
        "comments": 5,
        "replies": 5,
        "reposts": 2,
        "follows": 4,
        "posted_at": "2026-08-01T12:00:00Z",
    },
]


analyzer = PostResultAnalyzer()

analysis = analyzer.analyze(
    results,
    account_id="liver_manager",
    platform="threads",
)

assert set(
    analysis["by_content_route"]
) == {
    "original_text",
    "pdca_text",
}

assert set(
    analysis["by_generation_mode"]
) == {
    "original_text",
}

assert (
    analysis["by_content_route"]["pdca_text"]["count"]
    == 1
)

assert (
    analysis["by_generation_mode"]["original_text"]["count"]
    == 2
)


orchestrator = PDCAOrchestrator()

pdca = orchestrator.run(
    results,
    account_id="liver_manager",
    platform="threads",
)

route_comparison = pdca[
    "analysis"
]["content_route_comparison"]

assert set(route_comparison) == {
    "original_text",
    "pdca_text",
}

assert (
    route_comparison["pdca_text"][
        "generation_modes"
    ]
    == ["original_text"]
)

assert any(
    suggestion.get("type")
    == "content_route_mix"
    for suggestion in pdca[
        "improvement_suggestions"
    ]
)

assert all(
    suggestion["status"]
    == "WAITING_REVIEW"
    for suggestion in pdca[
        "improvement_suggestions"
    ]
)

assert all(
    suggestion["active"] is False
    for suggestion in pdca[
        "improvement_suggestions"
    ]
)


assert "content_route" in STRATEGY_DIMENSIONS
assert "generation_mode" in STRATEGY_DIMENSIONS

snapshots = [
    {
        "snapshot_id": "snapshot_original",
        "result_id": "result_original",
        "account_id": "liver_manager",
        "platform": "threads",
        "collection_window_hours": "24",
        "metrics_status": "MEASURED",
        "views": 100,
        "likes": 10,
        "comments": 2,
        "reposts": 1,
        "follows": 2,
        "collected_at": "2026-08-02T01:00:00Z",
    },
    {
        "snapshot_id": "snapshot_pdca",
        "result_id": "result_pdca_fallback",
        "account_id": "liver_manager",
        "platform": "threads",
        "collection_window_hours": "24",
        "metrics_status": "MEASURED",
        "views": 100,
        "likes": 25,
        "comments": 5,
        "reposts": 2,
        "follows": 4,
        "collected_at": "2026-08-02T12:00:00Z",
    },
]

observations = build_observations(
    results,
    snapshots,
    account_id="liver_manager",
)

assert len(observations) == 2

features_by_result = {
    row["result_id"]: row["features"]
    for row in observations
}

assert (
    features_by_result[
        "result_pdca_fallback"
    ]["content_route"]
    == "pdca_text"
)

assert (
    features_by_result[
        "result_pdca_fallback"
    ]["generation_mode"]
    == "original_text"
)

assert (
    features_by_result[
        "result_original"
    ]["content_route"]
    == "original_text"
)

legacy_result = {
    **results[0],
    "result_id": "legacy_route",
    "queue_id": "legacy_queue",
}

legacy_result.pop("content_route")

legacy_snapshot = {
    **snapshots[0],
    "snapshot_id": "legacy_snapshot",
    "result_id": "legacy_route",
}

legacy_observations = build_observations(
    [legacy_result],
    [legacy_snapshot],
    account_id="liver_manager",
)

assert (
    legacy_observations[0][
        "features"
    ]["content_route"]
    == "original_text"
)

print(
    "PASS "
    "test_route_level_pdca_analysis.py"
)
