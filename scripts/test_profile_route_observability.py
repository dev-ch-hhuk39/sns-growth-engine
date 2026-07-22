#!/usr/bin/env python3
"""Profile routing records provider/version/retryability without source URLs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from acquire_approved_source_posts import _route_provider_event  # noqa: E402

event = _route_provider_event(
    {"source_id": "src_lm_approved"},
    platform="tiktok",
    capability="tiktok.profile_posts",
    provider_name="tiktok_public_playwright",
    provider_version="public-html-v1",
    status="FAILED",
    reason="BackendFailure:rehydration_failed",
    retryable=True,
    attempt_count=2,
)
assert event["provider_name"] == "tiktok_public_playwright"
assert event["provider_version"] == "public-html-v1"
assert event["retryable"] == "true" and event["attempt_count"] == "2"
assert "url" not in " ".join(event.keys()).lower()
assert "http" not in event["reason"].lower()
print("PASS test_profile_route_observability.py")
