#!/usr/bin/env python3
"""Scheduled publishing requires live route evidence."""

from __future__ import annotations

from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
)
from final_production_contracts import (
    activation_evidence,
)
from scheduled_publish_activation_gate import (
    _decision,
    _scoped_text_decision,
    evaluate,
)


result = evaluate(use_sheets=False)

assert result["status"] == "BLOCKED"
assert result["DELIVERY_READY"] == "NO"
assert result["CONTENT_READY"] == "NO"
assert (
    result["AUTONOMOUS_PRODUCTION_READY"]
    == "NO"
)
assert result["SCHEDULED_PUBLISH"] == "OFF"
assert result["would_post"] is False


posted = []
jobs = []

for account_id in ACCOUNTS:
    for kind in ACTIVATION_CANARY_TYPES:
        canary_id = (
            "canary_fresh_activation_"
            f"{account_id}_{kind}"
        )

        posted.append(
            {
                "canary_id": canary_id,
                "account_id": account_id,
                "content_route": kind,
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
            }
        )

        jobs.extend(
            {
                "canary_id": canary_id,
                "window_hours": hours,
                "status": "SCHEDULED",
            }
            for hours in (
                24,
                72,
                168,
            )
        )


evidence = activation_evidence(
    posted,
    jobs,
)

assert evidence["expected_canary_count"] == 10
assert evidence["verified_canary_count"] == 10
assert evidence["DELIVERY_READY"] == "YES"
assert evidence["CONTENT_READY"] == "YES"
assert (
    evidence["AUTONOMOUS_PRODUCTION_READY"]
    == "NO"
)


config = {
    "kill_switch": False,
    (
        "production_publish_"
        "activation_approved"
    ): False,
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
assert fixture["DELIVERY_READY"] == "NO"
assert fixture["CONTENT_READY"] == "NO"
assert (
    fixture["AUTONOMOUS_PRODUCTION_READY"]
    == "NO"
)
assert fixture["SCHEDULED_PUBLISH"] == "OFF"
assert (
    "production_evidence_source_not_live"
    in fixture["blocked_reasons"]
)


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
assert (
    readiness["AUTONOMOUS_PRODUCTION_READY"]
    == "NO"
)
assert readiness["SCHEDULED_PUBLISH"] == "OFF"


runtime = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=True,
)

assert runtime["status"] == "BLOCKED"
assert (
    runtime["AUTONOMOUS_PRODUCTION_READY"]
    == "NO"
)
assert runtime["SCHEDULED_PUBLISH"] == "OFF"


config.update(
    {
        (
            "production_publish_"
            "activation_approved"
        ): True,
        "scheduled_publish_enabled": True,
    }
)

runtime_allowed = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=True,
)

assert runtime_allowed["status"] == "ALLOW"
assert (
    runtime_allowed[
        "AUTONOMOUS_PRODUCTION_READY"
    ]
    == "YES"
)
assert (
    runtime_allowed["SCHEDULED_PUBLISH"]
    == "ON"
)


config["kill_switch"] = True

killed = _decision(
    config,
    posted,
    jobs,
    evidence_source="READ_OK",
    require_persisted_activation=True,
)

assert killed["status"] == "BLOCKED"
assert (
    killed["AUTONOMOUS_PRODUCTION_READY"]
    == "NO"
)
assert killed["SCHEDULED_PUBLISH"] == "OFF"
assert (
    "kill_switch_enabled"
    in killed["blocked_reasons"]
)

scoped_integrity = {
    "status": "FAIL",
    "checks": [
        {"account_id": "night_scout", "canary_type": "original_text", "status": "PASS"},
        {"account_id": "liver_manager", "canary_type": "direct_reference_media", "status": "FAIL"},
    ],
}
scoped = _scoped_text_decision(
    {**config, "kill_switch": False},
    posted,
    jobs,
    evidence_source="READ_OK",
    canary_integrity=scoped_integrity,
    account_id="night_scout",
    post_type="original_text",
)
assert scoped["status"] == "ALLOW"
assert scoped["selected_evidence_canary_id"]

result_evidence_posted = [{
    "result_id": "threads_q_live_1",
    "account_id": "liver_manager",
    "content_route": "original_text",
    "status": "POSTED",
    "post_url": "https://www.threads.com/@example/post/live",
    "external_post_id": "live",
    "verification_status": "READ_AFTER_WRITE_PASS",
}]
result_evidence_jobs = [
    {
        "result_id": "threads_q_live_1",
        "window_hours": hours,
        "status": "SCHEDULED",
    }
    for hours in (24, 72, 168)
]
result_scoped = _scoped_text_decision(
    {**config, "kill_switch": False},
    result_evidence_posted,
    result_evidence_jobs,
    evidence_source="READ_OK",
    canary_integrity={"status": "FAIL", "checks": []},
    account_id="liver_manager",
    post_type="original_text",
)
assert result_scoped["status"] == "ALLOW", result_scoped
assert result_scoped["selected_evidence_canary_id"] == "result:threads_q_live_1"
assert result_scoped["selected_evidence_result_id"] == "threads_q_live_1"

wrong_route = _scoped_text_decision(
    {**config, "kill_switch": False},
    [],
    [],
    evidence_source="READ_OK",
    canary_integrity=scoped_integrity,
    account_id="night_scout",
    post_type="pdca_text",
)
assert wrong_route["status"] == "ALLOW"
assert wrong_route["historic_route_evidence_status"] == "NOT_YET_VERIFIED"
assert wrong_route["blocked_reasons"] == []

print(
    "PASS "
    "test_scheduled_publish_activation_gate.py"
)
