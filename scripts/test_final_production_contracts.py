#!/usr/bin/env python3

from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
    activation_canary_id,
)
from final_production_contracts import (
    activation_evidence,
    is_active_permission,
    source_integrity_report,
)

permission = {
    "account_id": "night_scout",
    "permission_status": "approved",
    "rights_status": "owned",
    "evidence_reference": "ledger",
    "revoked": "false",
    "allow_original_repost": "true",
    "allow_clip_repost": "true",
}

assert is_active_permission(
    permission,
    account_id="night_scout",
    operation="direct",
)

assert is_active_permission(
    permission,
    account_id="night_scout",
    operation="clip",
)

integrity = source_integrity_report(
    [
        {
            "source_post_id": "p",
            "platform": "threads",
            "canonical_post_url": (
                "https://www.threads.com/"
                "@a/post/b"
            ),
        }
    ],
    [
        {
            "source_post_id": "p",
            "canonical_post_url": (
                "https://www.threads.com/"
                "@a/post/b"
            ),
            "media_index": "0",
        }
    ],
)

assert integrity["status"] == "PASS"

posted = []
jobs = []

for account in ACCOUNTS:
    for kind in (
        ACTIVATION_CANARY_TYPES
    ):
        cid = activation_canary_id(
            account,
            kind,
        )

        posted.append(
            {
                "canary_id": cid,
                "account_id": account,
                "content_route": kind,
                "status": "POSTED",
                "post_url": (
                    "https://www.threads.com/"
                    "@a/post/b"
                ),
                "external_post_id": "1",
                "verification_status": (
                    "READ_AFTER_WRITE_PASS"
                ),
            }
        )

        jobs.extend(
            {
                "canary_id": cid,
                "window_hours": hours,
                "status": "SCHEDULED",
            }
            for hours in (
                24,
                72,
                168,
            )
        )

ready = activation_evidence(
    posted,
    jobs,
)

assert (
    ready["status"]
    == "READY_FOR_ACTIVATION"
)
assert ready["expected_canary_count"] == 10
assert ready["verified_canary_count"] == 10

assert (
    activation_evidence(
        posted[:-1],
        jobs,
    )["status"]
    == "BLOCKED"
)

fresh_posted = []
fresh_jobs = []

for account in ACCOUNTS:
    for kind in (
        ACTIVATION_CANARY_TYPES
    ):
        cid = (
            "canary_fresh_batch_001_"
            f"{account}_{kind}"
        )

        fresh_posted.append(
            {
                "canary_id": cid,
                "account_id": account,
                "content_route": kind,
                "status": "POSTED",
                "post_url": (
                    "https://www.threads.com/"
                    "@a/post/b"
                ),
                "external_post_id": "1",
                "verification_status": (
                    "READ_AFTER_WRITE_PASS"
                ),
            }
        )

        fresh_jobs.extend(
            {
                "canary_id": cid,
                "window_hours": hours,
                "status": "SCHEDULED",
            }
            for hours in (
                24,
                72,
                168,
            )
        )

fresh = activation_evidence(
    fresh_posted,
    fresh_jobs,
)

assert (
    fresh["status"]
    == "READY_FOR_ACTIVATION"
)
assert fresh["verified_canary_count"] == 10

print(
    "PASS "
    "test_final_production_contracts.py"
)
