#!/usr/bin/env python3
"""Run approved-source acquisition with batched, fail-soft observability writes.

Source posts, media, auxiliary rows, and discovery state remain critical and
fail closed. Backend health/history are operational telemetry: they are batched
to two Sheets writes and may degrade without converting a completed acquisition
into a failed run.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import acquire_approved_source_posts as acquisition


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _health_rows(results: list[dict[str, Any]], now: str) -> list[dict[str, Any]]:
    base = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    rows: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        name = str(result.get("selected_backend") or result.get("primary_backend") or "")
        if not name:
            continue
        passed = str(result.get("status", "")).upper() == "PASS"
        rows.append(
            {
                "backend_health_id": f"bh_{name}_{base + index}",
                "backend_name": name,
                "platform": result.get("platform", ""),
                "capability": result.get("capability", ""),
                "status": result.get("status", ""),
                "last_success_at": now if passed else "",
                "last_failure_at": "" if passed else now,
                "consecutive_failures": result.get("consecutive_failures", "0"),
                "cooldown_until": result.get("cooldown_until", ""),
                "average_duration_ms": "",
                "failure_reason": str(result.get("reason", ""))[:240],
                "selected_as_primary": str(not result.get("fallback_used", False)).lower(),
                "updated_at": now,
            }
        )
    return rows


def _history_rows(results: list[dict[str, Any]], now: str) -> list[dict[str, Any]]:
    base = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    rows: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        rows.append(
            {
                "routing_event_id": f"brh_{result.get('source_id', '')}_{base + index}",
                "source_id": result.get("source_id", ""),
                "platform": result.get("platform", ""),
                "capability": result.get("capability", ""),
                "primary_backend": result.get("primary_backend", ""),
                "selected_backend": result.get("selected_backend", ""),
                "fallback_used": str(result.get("fallback_used", False)).lower(),
                "shadow_backend_counts": json.dumps(result.get("shadow_backend_counts", {}), sort_keys=True),
                "status": result.get("status", ""),
                "reason": str(result.get("reason", ""))[:240],
                "selected_backend_version": result.get("selected_backend_version", ""),
                "attempt_count": str(result.get("attempt_count") or 1),
                "retryable": str(bool(result.get("retryable", result.get("status") != "PASS"))).lower(),
                "created_at": now,
            }
        )
    return rows


def _append_batch(
    client: Any,
    logical: str,
    rows: list[dict[str, Any]],
    label: str,
) -> int:
    if not rows:
        return 0
    ws, headers, _existing = acquisition._headers(client, logical)
    values = [
        [acquisition.bounded_cell(row.get(header, "")) for header in headers]
        for row in rows
    ]
    client._call_with_rate_limit_retry(
        label,
        lambda: ws.append_rows(values, value_input_option="USER_ENTERED"),
    )
    return len(rows)


def persist_observability_fail_soft(
    client: Any,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    now = _now()
    outcome: dict[str, Any] = {
        "status": "PASS",
        "saved_backend_health": 0,
        "saved_backend_routing_history": 0,
        "errors": [],
    }
    batches = (
        (
            "backend_health",
            _health_rows(results, now),
            "saved_backend_health",
            "append_rows:backend_health:acquisition",
        ),
        (
            "backend_routing_history",
            _history_rows(results, now),
            "saved_backend_routing_history",
            "append_rows:backend_routing_history:acquisition",
        ),
    )
    for logical, rows, count_key, label in batches:
        try:
            outcome[count_key] = _append_batch(client, logical, rows, label)
        except Exception as exc:  # telemetry must never invalidate committed source data
            outcome["status"] = "DEGRADED"
            outcome["errors"].append(
                {
                    "logical": logical,
                    "error_type": type(exc).__name__,
                    "reason": str(exc)[:240],
                }
            )
    if outcome["status"] != "PASS":
        print(
            json.dumps({"acquisition_observability": outcome}, ensure_ascii=False),
            file=sys.stderr,
        )
    return outcome


def install_failsoft_observability() -> None:
    original_run = acquisition.run
    state: dict[str, Any] = {"status": "NOT_RUN"}

    def safe_persist(client: Any, results: list[dict[str, Any]]) -> dict[str, Any]:
        outcome = persist_observability_fail_soft(client, results)
        state.clear()
        state.update(outcome)
        return outcome

    def run_with_observability(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original_run(*args, **kwargs)
        result["observability"] = dict(state)
        return result

    acquisition.persist_observability = safe_persist
    acquisition.run = run_with_observability


def main() -> int:
    install_failsoft_observability()
    return acquisition.main()


if __name__ == "__main__":
    raise SystemExit(main())
