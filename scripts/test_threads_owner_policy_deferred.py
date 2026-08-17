#!/usr/bin/env python3
"""Latest owner policy activates bounded public Threads reference discovery."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.capability_registry import CapabilityRegistry  # noqa: E402
from acquisition.factory import build_router  # noqa: E402
from acquisition_doctor import build_report  # noqa: E402

routing = json.loads(
    (ROOT / "config/source_backend_routing.json").read_text(encoding="utf-8")
)
completion = json.loads(
    (ROOT / "config/reference_first_completion.json").read_text(encoding="utf-8")
)
registry = CapabilityRegistry.load()
doctor = build_report(registry)
router = build_router()
route = routing["routes"]["threads.profile_posts"]

checks = {
    "three-stage route": route["primary"] == "threads_cli_public"
    and route["fallbacks"]
    == ["threads_logged_out_graphql", "threads_public_screen"],
    "router registers route": "threads.profile_posts" in router.routes,
    "no auth in three stages": all(
        not registry.get(name).requires_auth
        for name in [route["primary"], *route["fallbacks"]]
    ),
    "Threads active in completion contract": "threads"
    in completion["active_acquisition_platforms"],
    "no deferred reference platform": completion["deferred_reference_acquisition"]
    == {},
    "doctor reports no deferred Threads": doctor["deferred_platforms"] == [],
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
