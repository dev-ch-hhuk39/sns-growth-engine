#!/usr/bin/env python3
"""Threads reference collection must fail closed under the owner OSS policy."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import collect_source_posts as collector  # noqa: E402


result = collector.fetch_threads_account_posts(
    {"source_id": "src", "source_url": "https://www.threads.com/@target"},
    limit=2,
)

checks = {
    "owner-policy deferred": result["status"] == "DEFERRED_OSS_CANDIDATE",
    "exact deferred reason": result["reason"]
    == "NO_APPROVED_BACKEND_ONLY_GITHUB_OSS_ROUTE_CURRENTLY_PROVEN",
    "no rows fabricated": result["rows"] == [],
    "no active backend": result["backend"] == ""
    and result["fallback_used"] is False,
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
