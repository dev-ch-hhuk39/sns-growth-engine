#!/usr/bin/env python3
"""Owner policy keeps Threads history while excluding it from active acquisition."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.capability_registry import CapabilityRegistry  # noqa: E402
from acquisition_doctor import build_report  # noqa: E402
from acquire_approved_source_posts import run  # noqa: E402


routing = json.loads(
    (ROOT / "config/source_backend_routing.json").read_text(encoding="utf-8")
)
completion = json.loads(
    (ROOT / "config/reference_first_completion.json").read_text(encoding="utf-8")
)
registry = CapabilityRegistry.load()
doctor = build_report(registry)
deferred_run = run(
    "all",
    "threads",
    5,
    apply=False,
    shadow=False,
    reference_only=True,
    verify_network=True,
)

threads_backend_ids = (
    "threads_public_http",
    "threads_oembed_detail",
    "threads_search_index",
    "threads_graph_public_discovery",
    "threads_hasya_userscript",
    "threads_zeeshan_playwright",
    "threads_vdite_playwright",
    "threads_galih_playwright",
)
threads_policy = completion["deferred_reference_acquisition"]["threads"]
serialized_doctor = json.dumps(doctor, ensure_ascii=False)

checks = {
    "no active Threads route": not any(
        capability.startswith("threads.") for capability in routing["routes"]
    ),
    "all historical Threads backends are owner-policy inactive": all(
        registry.get(backend_id).role == "NOT_USED_BY_OWNER_POLICY"
        for backend_id in threads_backend_ids
    ),
    "doctor requires no Threads token": "THREADS_DISCOVERY_ACCESS_TOKEN"
    not in serialized_doctor,
    "doctor reports deferred Threads": doctor["deferred_platforms"]
    == [
        {
            "platform": "threads",
            "status": "DEFERRED_OSS_CANDIDATE",
            "reason": "NO_APPROVED_BACKEND_ONLY_GITHUB_OSS_ROUTE_CURRENTLY_PROVEN",
            "auth_required": False,
        }
    ],
    "safe deferred skip": deferred_run["status"] == "DEFERRED_OSS_CANDIDATE"
    and deferred_run["network_fetch"] is False,
    "future OSS re-enable model recorded": bool(
        threads_policy.get("future_reenable_model")
    ),
}

for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
