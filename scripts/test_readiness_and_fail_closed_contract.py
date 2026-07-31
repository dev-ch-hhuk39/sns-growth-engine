#!/usr/bin/env python3
"""Readiness dimensions and media failures must remain fail closed."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from final_production_contracts import (
    activation_evidence,
    canary_id,
)
from scheduled_publish_activation_gate import _decision

KINDS = (
    "original_text",
    "reference_text",
    "direct_image",
    "direct_video",
    "direct_carousel",
    "approved_source_clip",
)

empty = activation_evidence([], [])

assert empty["DELIVERY_READY"] == "NO"
assert empty["CONTENT_READY"] == "NO"
assert empty["AUTONOMOUS_PRODUCTION_READY"] == "NO"

posted = []
jobs = []

for account_id in ("night_scout", "liver_manager"):
    for kind in KINDS:
        evidence_id = (
            f"canary_production_evidence_"
            f"{account_id}_{kind}"
        )

        posted.append({
            "canary_id": evidence_id,
            "account_id": account_id,
            "content_type": kind,
            "status": "POSTED",
            "post_url": (
                "https://www.threads.com/"
                "@example/post/example"
            ),
            "external_post_id": "example",
            "verification_status": (
                "READ_AFTER_WRITE_PASS"
            ),
        })

        for window_hours in (24, 72, 168):
            jobs.append({
                "canary_id": evidence_id,
                "window_hours": window_hours,
                "status": "SCHEDULED",
            })

complete = activation_evidence(posted, jobs)

assert complete["DELIVERY_READY"] == "YES"
assert complete["CONTENT_READY"] == "YES"
assert complete["AUTONOMOUS_PRODUCTION_READY"] == "NO"

config = {
    "kill_switch": False,
    "production_publish_activation_approved": False,
    "scheduled_publish_enabled": False,
}

fixture = _decision(
    config,
    posted,
    jobs,
    evidence_source="FIXTURE",
    require_persisted_activation=False,
)

assert fixture["status"] == "BLOCKED"
assert fixture["CONTENT_READY"] == "NO"
assert (
    "production_evidence_source_not_live"
    in fixture["blocked_reasons"]
)

live_readiness = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=False,
)

assert live_readiness["status"] == "ALLOW"
assert live_readiness["DELIVERY_READY"] == "YES"
assert live_readiness["CONTENT_READY"] == "YES"
assert (
    live_readiness["AUTONOMOUS_PRODUCTION_READY"]
    == "NO"
)
assert live_readiness["SCHEDULED_PUBLISH"] == "OFF"

runtime_blocked = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=True,
)

assert runtime_blocked["status"] == "BLOCKED"
assert (
    runtime_blocked["AUTONOMOUS_PRODUCTION_READY"]
    == "NO"
)
assert runtime_blocked["SCHEDULED_PUBLISH"] == "OFF"

config.update({
    "production_publish_activation_approved": True,
    "scheduled_publish_enabled": True,
})

runtime_allowed = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=True,
)

assert runtime_allowed["status"] == "ALLOW"
assert (
    runtime_allowed["AUTONOMOUS_PRODUCTION_READY"]
    == "YES"
)
assert runtime_allowed["SCHEDULED_PUBLISH"] == "ON"

autonomous = json.loads(
    (ROOT / "config/autonomous_mode.json").read_text(
        encoding="utf-8"
    )
)

assert (
    autonomous["production_publish_activation_approved"]
    is False
)
assert autonomous["scheduled_publish_enabled"] is False

pipeline = (
    ROOT / "scripts/run_media_production_pipeline.py"
).read_text(encoding="utf-8")

for required_status in (
    "BLOCKED_NO_APPROVED_SOURCE",
    "BLOCKED_NO_SOURCE_MEDIA",
    "BLOCKED_MEDIA_DOWNLOAD_FAILED",
    "BLOCKED_CLIP_FAILED",
    "BLOCKED_TONE_FAILED",
    "REVIEW_REQUIRED",
):
    assert required_status in pipeline, required_status

assert '"status": "FAILED_DOWNLOAD"' not in pipeline
assert '"status": "FAILED_CUT"' not in pipeline

audit = (
    ROOT / "scripts/audit_existing_canary_evidence.py"
).read_text(encoding="utf-8")

assert "INVALID_CONTENT_CANARY" in audit

inventory = (
    ROOT / "scripts/build_live_canary_inventory.py"
).read_text(encoding="utf-8")

assert "INVALID_CONTENT_CANARY" in inventory

assert canary_id(
    "night_scout",
    "approved_source_clip",
) == "canary_night_scout_approved_source_clip"

print("PASS test_readiness_and_fail_closed_contract.py")
