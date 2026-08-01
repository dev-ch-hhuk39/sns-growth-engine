#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "scripts"),
)

from final_production_contracts import (
    ACCOUNTS,
    CANARY_TYPES,
    canary_id,
)
from scheduled_publish_activation_gate import (
    _decision,
)


def posted_rows() -> list[dict[str, object]]:
    return [
        {
            "canary_id": canary_id(
                account,
                kind,
            ),
            "account_id": account,
            "canary_type": kind,
            "status": "POSTED",
            "post_url": ("https://www.threads.net/" f"@test/post/{account}_{kind}"),
            "external_post_id": (f"{account}_{kind}"),
            "verification_status": ("READ_AFTER_WRITE_PASS"),
        }
        for account in ACCOUNTS
        for kind in CANARY_TYPES
    ]


def metric_rows() -> list[dict[str, object]]:
    return [
        {
            "canary_id": canary_id(
                account,
                kind,
            ),
            "window_hours": window,
            "status": "SCHEDULED",
        }
        for account in ACCOUNTS
        for kind in CANARY_TYPES
        for window in (
            24,
            72,
            168,
        )
    ]


invalid_types = {
    "direct_image",
    "direct_video",
    "direct_carousel",
}

invalid_integrity = {
    "status": "FAIL",
    "checks": [
        {
            "canary_id": canary_id(
                account,
                kind,
            ),
            "account_id": account,
            "canary_type": kind,
            "status": ("FAIL" if kind in invalid_types else "PASS"),
            "reasons": (["parent_not_individual_post"] if kind in invalid_types else []),
        }
        for account in ACCOUNTS
        for kind in CANARY_TYPES
    ],
}

config = {
    "kill_switch": False,
    "production_publish_activation_approved": False,
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

assert "canary_source_integrity_incomplete" in blocked["blocked_reasons"]

evidence = blocked["activation_evidence"]

assert evidence["verified_canary_count"] == 6, evidence

assert len(evidence["missing_or_invalid_" "canary_source_integrity"]) == 6, evidence

valid_integrity = {
    "status": "PASS",
    "checks": [
        {
            "canary_id": canary_id(
                account,
                kind,
            ),
            "account_id": account,
            "canary_type": kind,
            "status": "PASS",
            "reasons": [],
        }
        for account in ACCOUNTS
        for kind in CANARY_TYPES
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

assert allowed["activation_evidence"]["verified_canary_count"] == 12

print("PASS " "test_activation_rejects_invalid_" "canary_integrity.py")
