#!/usr/bin/env python3

from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
    activation_canary_id,
)
from scheduled_publish_activation_gate import (
    _decision,
)


def posted_rows():
    return [
        {
            "canary_id": (
                activation_canary_id(
                    account,
                    kind,
                )
            ),
            "account_id": account,
            "content_route": kind,
            "status": "POSTED",
            "post_url": (
                "https://www.threads.com/"
                f"@test/post/{account}_{kind}"
            ),
            "external_post_id": (
                f"{account}_{kind}"
            ),
            "verification_status": (
                "READ_AFTER_WRITE_PASS"
            ),
        }
        for account in ACCOUNTS
        for kind in ACTIVATION_CANARY_TYPES
    ]


def metric_rows():
    return [
        {
            "canary_id": (
                activation_canary_id(
                    account,
                    kind,
                )
            ),
            "window_hours": window,
            "status": "SCHEDULED",
        }
        for account in ACCOUNTS
        for kind in ACTIVATION_CANARY_TYPES
        for window in (
            24,
            72,
            168,
        )
    ]


invalid_integrity = {
    "status": "FAIL",
    "checks": [
        {
            "canary_id": (
                activation_canary_id(
                    account,
                    kind,
                )
            ),
            "account_id": account,
            "canary_type": kind,
            "status": (
                "FAIL"
                if kind
                == "direct_reference_media"
                else "PASS"
            ),
            "reasons": (
                [
                    (
                        "parent_not_"
                        "individual_post"
                    )
                ]
                if kind
                == "direct_reference_media"
                else []
            ),
        }
        for account in ACCOUNTS
        for kind in ACTIVATION_CANARY_TYPES
    ],
}

config = {
    "kill_switch": False,
    (
        "production_publish_"
        "activation_approved"
    ): False,
    "scheduled_publish_enabled": False,
}

blocked = _decision(
    config,
    posted_rows(),
    metric_rows(),
    evidence_source="READ_OK",
    require_persisted_activation=False,
    canary_integrity=invalid_integrity,
)

assert blocked["status"] == "BLOCKED"

evidence = blocked[
    "activation_evidence"
]

assert evidence[
    "verified_canary_count"
] == 8

assert len(
    evidence[
        (
            "missing_or_invalid_"
            "canary_source_integrity"
        )
    ]
) == 2

valid_integrity = {
    "status": "PASS",
    "checks": [
        {
            "canary_id": (
                activation_canary_id(
                    account,
                    kind,
                )
            ),
            "account_id": account,
            "canary_type": kind,
            "status": "PASS",
            "reasons": [],
        }
        for account in ACCOUNTS
        for kind in ACTIVATION_CANARY_TYPES
    ],
}

allowed = _decision(
    config,
    posted_rows(),
    metric_rows(),
    evidence_source="READ_OK",
    require_persisted_activation=False,
    canary_integrity=valid_integrity,
)

assert allowed["status"] == "ALLOW"

assert allowed[
    "activation_evidence"
]["verified_canary_count"] == 10

print(
    "PASS "
    "test_activation_rejects_"
    "invalid_canary_integrity.py"
)
