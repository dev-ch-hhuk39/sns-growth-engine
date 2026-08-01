#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import ingest_direct_reference_media_reliable as module


def owner_attestation(**overrides):
    row = {
        "source_id": "source-1",
        "usage_mode": "direct_media_reuse",
        "allow_download": "true",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true",
        "allow_new_caption": "true",
        "evidence_type": "owner_attestation",
        "evidence_reference": "global_owner_attestation_v1",
        "approved_by": "Chadult株式会社",
        "approved_at": "2026-07-18T09:00:00+00:00",
        "updated_at": "2026-07-18T09:00:00+00:00",
        "revoked": "false",
        "rights_status": "",
        "permission_status": "",
    }

    row.update(overrides)

    return row


assert module.permission_ok_from_rows(
    [owner_attestation()],
    "source-1",
)

assert module.core.permission_ok_from_rows(
    [owner_attestation()],
    "source-1",
)

assert not module.permission_ok_from_rows(
    [
        owner_attestation(
            evidence_reference="",
        )
    ],
    "source-1",
)

assert not module.permission_ok_from_rows(
    [
        owner_attestation(
            approved_by="",
        )
    ],
    "source-1",
)

assert not module.permission_ok_from_rows(
    [
        owner_attestation(
            permission_status="denied",
        )
    ],
    "source-1",
)

assert not module.permission_ok_from_rows(
    [
        owner_attestation(
            revoked="true",
        )
    ],
    "source-1",
)

assert not module.permission_ok_from_rows(
    [
        owner_attestation(
            usage_mode="reference_only",
        )
    ],
    "source-1",
)

assert module.permission_ok_from_rows(
    [
        owner_attestation(
            permission_status="approved",
            rights_status="licensed",
            usage_mode="licensed_reuse",
        )
    ],
    "source-1",
)

older = owner_attestation(
    updated_at="2026-07-18T09:00:00+00:00",
)

newer_revoked = owner_attestation(
    updated_at="2026-07-19T09:00:00+00:00",
    revoked="true",
)

assert not module.permission_ok_from_rows(
    [
        older,
        newer_revoked,
    ],
    "source-1",
)

print(
    "PASS "
    "test_direct_media_permission_normalization.py"
)
