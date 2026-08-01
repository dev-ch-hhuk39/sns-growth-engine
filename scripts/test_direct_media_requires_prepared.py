#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_direct_reference_media_pipeline_batched as module


previous = os.environ.get(
    "REQUIRE_PREPARED"
)

try:
    os.environ.pop(
        "REQUIRE_PREPARED",
        None,
    )

    normal = module._normalize_prepare_only_outcome(
        {
            "status": "NO_POST",
            "blocked_reasons": [
                "no_candidate",
            ],
        },
        prepare_only=True,
    )

    assert normal["status"] == "NO_READY_MEDIA"

    os.environ[
        "REQUIRE_PREPARED"
    ] = "true"

    failed = module._normalize_prepare_only_outcome(
        {
            "status": "NO_POST",
            "blocked_reasons": [
                "no_candidate",
            ],
        },
        prepare_only=True,
    )

    assert failed["status"] == "FAILED_READY_REQUIRED"
    assert failed["preparation_status"] == "NO_POST"
    assert failed["would_post"] is False

    assert (
        "confirmed_preparation_did_not_create_ready_inventory"
        in failed["blocked_reasons"]
    )

    prepared = module._normalize_prepare_only_outcome(
        {
            "status": "PREPARED",
            "queue_id": "queue-1",
            "would_post": False,
        },
        prepare_only=True,
    )

    assert prepared["status"] == "PREPARED"
    assert prepared["queue_id"] == "queue-1"

finally:
    if previous is None:
        os.environ.pop(
            "REQUIRE_PREPARED",
            None,
        )
    else:
        os.environ[
            "REQUIRE_PREPARED"
        ] = previous

print(
    "PASS "
    "test_direct_media_requires_prepared.py"
)
