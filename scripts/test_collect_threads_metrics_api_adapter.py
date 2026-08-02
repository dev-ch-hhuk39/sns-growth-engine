#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/collect_threads_metrics.py"
)

spec = importlib.util.spec_from_file_location(
    "collect_metrics_api_test",
    SCRIPT,
)

module = importlib.util.module_from_spec(
    spec
)

assert spec.loader is not None
spec.loader.exec_module(module)


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def read(self):
        return json.dumps(
            {
                "data": [
                    {
                        "name": "views",
                        "total_value": {
                            "value": 120,
                        },
                    },
                    {
                        "name": "likes",
                        "total_value": {
                            "value": 12,
                        },
                    },
                    {
                        "name": "replies",
                        "total_value": {
                            "value": 3,
                        },
                    },
                    {
                        "name": "reposts",
                        "total_value": {
                            "value": 2,
                        },
                    },
                    {
                        "name": "quotes",
                        "total_value": {
                            "value": 1,
                        },
                    },
                ]
            }
        ).encode("utf-8")


captured = {}


def fake_urlopen(
    request,
    timeout,
):
    captured["url"] = request.full_url
    captured["authorization"] = (
        request.headers.get(
            "Authorization"
        )
    )
    captured["timeout"] = timeout
    return FakeResponse()


original = (
    module.urllib.request.urlopen
)

module.urllib.request.urlopen = (
    fake_urlopen
)

try:
    metrics, confidence, error = (
        module.collect_api_threads_metrics(
            {
                "external_post_id": (
                    "123456789"
                )
            },
            "secret-token",
        )
    )
finally:
    module.urllib.request.urlopen = (
        original
    )

assert metrics["views"] == 120
assert metrics["likes"] == 12
assert metrics["comments"] == 3
assert metrics["reposts"] == 2
assert metrics["quotes"] == 1

assert metrics["profile_clicks"] is None
assert metrics["follows"] is None
assert metrics["line_adds"] is None

assert confidence == "high"
assert error == ""

assert "secret-token" not in captured["url"]
assert (
    captured["authorization"]
    == "Bearer secret-token"
)

snapshot = module.build_snapshot(
    row={
        "result_id": "r1",
        "account_id": "night_scout",
    },
    source="api",
    confidence=confidence,
    metrics=metrics,
    memo="test",
)

assert (
    snapshot["metrics_status"]
    == "MEASURED"
)

assert (
    snapshot["collection_status"]
    == "AVAILABLE"
)

missing, confidence, error = (
    module.collect_api_threads_metrics(
        {
            "external_post_id": (
                "123456789"
            )
        },
        "",
    )
)

assert all(
    value is None
    for value in missing.values()
)

assert confidence == "none"

assert (
    error
    == "threads_access_token_missing"
)

print(
    "PASS "
    "test_collect_threads_metrics_api_adapter.py"
)
