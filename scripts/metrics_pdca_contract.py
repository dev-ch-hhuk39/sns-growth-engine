#!/usr/bin/env python3
"""Select trusted metric observations for human-reviewed PDCA only."""
from __future__ import annotations

from typing import Any


METRIC_FIELDS = ("views", "likes", "comments", "reposts", "quotes", "profile_clicks", "follows", "line_adds")


def measured_results_only(rows: list[dict[str, Any]], *, account_id: str, platform: str) -> list[dict[str, Any]]:
    """Return only explicitly MEASURED rows; null/unknown values remain untouched."""
    selected: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("account_id", "")) != account_id:
            continue
        if str(row.get("platform", "")).lower() != platform.lower():
            continue
        if str(row.get("metrics_status", "")).upper() != "MEASURED":
            continue
        selected.append(dict(row))
    return selected


def pdca_input_summary(rows: list[dict[str, Any]]) -> dict[str, int | str]:
    known_values = sum(1 for row in rows for field in METRIC_FIELDS if row.get(field) not in (None, ""))
    return {
        "metrics_status": "MEASURED_ONLY" if rows else "NO_MEASURED_RESULTS",
        "measured_result_count": len(rows),
        "known_metric_value_count": known_values,
    }
