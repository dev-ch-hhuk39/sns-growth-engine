#!/usr/bin/env python3
"""Scheduled publishing requires live evidence and persisted activation."""
from __future__ import annotations

from final_production_contracts import activation_evidence
from scheduled_publish_activation_gate import _decision, evaluate


# No live Sheets evidence must remain fail closed.
result = evaluate(use_sheets=False)

assert result["status"] == "BLOCKED"
assert result["DELIVERY_READY"] == "NO"
assert result["CONTENT_READY"] == "NO"
assert result["AUTONOMOUS_PRODUCTION_READY"] == "NO"
assert result["SCHEDULED_PUBLISH"] == "OFF"
assert result["would_post"] is False


posted = []
jobs = []

for account_id in ("night_scout", "liver_manager"):
    for kind in (
        "original_text",
        "reference_text",
        "direct_image",
        "direct_video",
        "direct_carousel",
        "approved_source_clip",
    ):
        canary_id = (
            f"canary_fresh_activation_"
            f"{account_id}_{kind}"
        )

        posted.append({
            "canary_id": canary_id,
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

        jobs.extend({
            "canary_id": canary_id,
            "window_hours": hours,
            "status": "SCHEDULED",
        } for hours in (24, 72, 168))


evidence = activation_evidence(posted, jobs)

assert evidence["DELIVERY_READY"] == "YES"
assert evidence["CONTENT_READY"] == "YES"
assert evidence["AUTONOMOUS_PRODUCTION_READY"] == "NO"


config = {
    "kill_switch": False,
    "production_publish_activation_approved": False,
    "scheduled_publish_enabled": False,
}


# Structurally complete fixture evidence is not production evidence.
fixture = _decision(
    config,
    posted,
    jobs,
    evidence_source="FIXTURE",
    require_persisted_activation=False,
)

assert fixture["status"] == "BLOCKED"
assert fixture["DELIVERY_READY"] == "NO"
assert fixture["CONTENT_READY"] == "NO"
assert fixture["AUTONOMOUS_PRODUCTION_READY"] == "NO"
assert fixture["SCHEDULED_PUBLISH"] == "OFF"
assert (
    "production_evidence_source_not_live"
    in fixture["blocked_reasons"]
)


# Live read-after-write evidence can pass pre-activation readiness,
# but it cannot declare autonomous production ready yet.
readiness = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=False,
)

assert readiness["status"] == "ALLOW"
assert readiness["DELIVERY_READY"] == "YES"
assert readiness["CONTENT_READY"] == "YES"
assert readiness["AUTONOMOUS_PRODUCTION_READY"] == "NO"
assert readiness["SCHEDULED_PUBLISH"] == "OFF"


# Runtime remains blocked until both persisted activation flags are on.
runtime = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=True,
)

assert runtime["status"] == "BLOCKED"
assert runtime["AUTONOMOUS_PRODUCTION_READY"] == "NO"
assert runtime["SCHEDULED_PUBLISH"] == "OFF"


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


config["kill_switch"] = True

killed = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=True,
)

assert killed["status"] == "BLOCKED"
assert killed["AUTONOMOUS_PRODUCTION_READY"] == "NO"
assert killed["SCHEDULED_PUBLISH"] == "OFF"
assert "kill_switch_enabled" in killed["blocked_reasons"]

print("PASS test_scheduled_publish_activation_gate.py")
