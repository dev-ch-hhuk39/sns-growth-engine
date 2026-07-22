#!/usr/bin/env python3
"""A routed profile acquisition must fail closed after bounded backends fail."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.router import AdapterRouter, BackendFailure, BackendRoute  # noqa: E402


class FailingAdapter:
    backend_version = "fixture-v1"

    def __init__(self, name: str):
        self.backend_name = name

    def acquire(self, _source, *, limit):
        raise BackendFailure("rehydration_failed")


router = AdapterRouter(
    {"primary": FailingAdapter("primary"), "fallback": FailingAdapter("fallback")},
    {"tiktok.profile_posts": BackendRoute("tiktok.profile_posts", "primary", ("fallback",), cooldown_seconds=1)},
)
try:
    router.route("tiktok.profile_posts", {"source_url": "https://www.tiktok.com/@approved.creator"}, limit=3)
    raised = False
    reason = ""
except BackendFailure as exc:
    raised = True
    reason = str(exc)

assert raised and "all_backends_failed" in reason and "primary" in reason and "fallback" in reason
assert all(row["consecutive_failures"] == 1 for row in router.health_rows())
assert "approved.creator" not in reason
print("PASS test_acquisition_router_all_backends_fail.py")
