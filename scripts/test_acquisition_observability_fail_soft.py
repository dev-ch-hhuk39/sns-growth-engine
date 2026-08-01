#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import acquire_approved_source_posts_failsoft as failsoft


class FakeWorksheet:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.append_rows_calls: list[list[list[object]]] = []

    def append_rows(self, values, value_input_option="USER_ENTERED"):
        assert value_input_option == "USER_ENTERED"
        if self.fail:
            raise RuntimeError("429 write quota")
        self.append_rows_calls.append(values)

    def append_row(self, *_args, **_kwargs):
        raise AssertionError("observability must use append_rows, not append_row")


class FakeClient:
    def _call_with_rate_limit_retry(self, _label, fn):
        return fn()


RESULTS = [
    {
        "source_id": "source_one",
        "platform": "threads",
        "capability": "threads.profile_posts",
        "primary_backend": "threads_public",
        "selected_backend": "threads_public",
        "selected_backend_version": "1",
        "status": "PASS",
        "fallback_used": False,
        "attempt_count": 1,
    },
    {
        "source_id": "source_two",
        "platform": "tiktok",
        "capability": "tiktok.profile_posts",
        "primary_backend": "yt_dlp",
        "selected_backend": "yt_dlp",
        "selected_backend_version": "1",
        "status": "FAILED",
        "reason": "temporary backend failure",
        "fallback_used": False,
        "attempt_count": 2,
        "retryable": True,
    },
]

HEALTH_HEADERS = [
    "backend_health_id",
    "backend_name",
    "platform",
    "capability",
    "status",
    "last_success_at",
    "last_failure_at",
    "consecutive_failures",
    "cooldown_until",
    "average_duration_ms",
    "failure_reason",
    "selected_as_primary",
    "updated_at",
]

HISTORY_HEADERS = [
    "routing_event_id",
    "source_id",
    "platform",
    "capability",
    "primary_backend",
    "selected_backend",
    "fallback_used",
    "shadow_backend_counts",
    "status",
    "reason",
    "selected_backend_version",
    "attempt_count",
    "retryable",
    "created_at",
]


def run_case(*, health_fails: bool):
    sheets = {
        "backend_health": FakeWorksheet(fail=health_fails),
        "backend_routing_history": FakeWorksheet(),
    }
    headers = {
        "backend_health": HEALTH_HEADERS,
        "backend_routing_history": HISTORY_HEADERS,
    }
    original_headers = failsoft.acquisition._headers
    failsoft.acquisition._headers = (
        lambda _client, logical: (sheets[logical], headers[logical], [])
    )
    try:
        outcome = failsoft.persist_observability_fail_soft(FakeClient(), RESULTS)
    finally:
        failsoft.acquisition._headers = original_headers
    return outcome, sheets


outcome, sheets = run_case(health_fails=False)
assert outcome["status"] == "PASS"
assert outcome["saved_backend_health"] == 2
assert outcome["saved_backend_routing_history"] == 2
assert len(sheets["backend_health"].append_rows_calls) == 1
assert len(sheets["backend_routing_history"].append_rows_calls) == 1
assert len(sheets["backend_health"].append_rows_calls[0]) == 2
assert len(sheets["backend_routing_history"].append_rows_calls[0]) == 2

outcome, sheets = run_case(health_fails=True)
assert outcome["status"] == "DEGRADED"
assert outcome["saved_backend_health"] == 0
assert outcome["saved_backend_routing_history"] == 2
assert outcome["errors"][0]["logical"] == "backend_health"
assert len(sheets["backend_routing_history"].append_rows_calls) == 1

original_run = failsoft.acquisition.run
original_persist = failsoft.acquisition.persist_observability
failsoft.acquisition.run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
    RuntimeError("critical source persistence failure")
)
try:
    failsoft.install_failsoft_observability()
    try:
        failsoft.acquisition.run("all", "all", 30, apply=True, shadow=False)
    except RuntimeError as exc:
        assert str(exc) == "critical source persistence failure"
    else:
        raise AssertionError("critical acquisition failures must remain fail-closed")
finally:
    failsoft.acquisition.run = original_run
    failsoft.acquisition.persist_observability = original_persist

workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/account-acquisition.yml").read_text(encoding="utf-8")
assert "acquire_approved_source_posts_failsoft.py" in workflow
assert "PUBLISH_ENABLED: \"false\"" in workflow
assert "ALLOW_REAL_THREADS_POST: \"false\"" in workflow
assert "ALLOW_MEDIA_POSTS: \"false\"" in workflow

print("PASS test_acquisition_observability_fail_soft.py")
