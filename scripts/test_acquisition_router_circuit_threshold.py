#!/usr/bin/env python3
"""A single source failure must not open a route-wide profile circuit."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.router import AdapterRouter, BackendFailure, BackendRoute  # noqa: E402


class FlakyAdapter:
    backend_version = "fixture-v1"

    def __init__(self, name: str, failures: int):
        self.backend_name = name
        self.failures = failures
        self.calls = 0

    def acquire(self, _source, *, limit):
        self.calls += 1
        if self.calls <= self.failures:
            raise BackendFailure("source_specific_transient_failure")
        return [self.backend_name]


primary = FlakyAdapter("primary", failures=1)
fallback = FlakyAdapter("fallback", failures=0)
route = BackendRoute("threads.profile_posts", "primary", ("fallback",), cooldown_seconds=900, circuit_failure_threshold=3)
router = AdapterRouter({"primary": primary, "fallback": fallback}, {"threads.profile_posts": route})

first = router.route("threads.profile_posts", {"source_id": "first"}, limit=1)
second = router.route("threads.profile_posts", {"source_id": "second"}, limit=1)

checks = {
    "first source uses fallback": first.backend_name == "fallback",
    "second source retries primary": second.backend_name == "primary",
    "primary was not circuit-opened after one failure": primary.calls == 2,
    "fallback only ran for failing source": fallback.calls == 1,
    "route config threshold is three": route.circuit_failure_threshold == 3,
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
