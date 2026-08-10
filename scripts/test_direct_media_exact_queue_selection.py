#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_direct_reference_media_pipeline as pipeline  # noqa: E402


target_date = "2026-08-01"
slot_id = "ns_1800_direct_media"

rows = [
    {
        "queue_id": "q-first",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "READY",
        "generation_mode": (
            "direct_reference_media"
        ),
        "slot_id": slot_id,
        "business_date_jst": target_date,
        "priority": "1",
        "created_at": (
            "2026-08-01T00:00:00+00:00"
        ),
        "media_type": "video",
    },
    {
        "queue_id": "q-exact",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "READY",
        "generation_mode": (
            "direct_reference_media"
        ),
        "slot_id": slot_id,
        "business_date_jst": target_date,
        "priority": "2",
        "created_at": (
            "2026-08-01T00:01:00+00:00"
        ),
        "media_type": "video",
    },
]

pipeline.business_date = lambda: target_date

pipeline.existing_slot_status = (
    lambda *_args, **_kwargs: ""
)

pipeline._records = (
    lambda _client, logical: (
        [dict(row) for row in rows]
        if logical == "queue"
        else []
    )
)

attempted = []


def process_one(
    _client,
    row,
    *,
    dry_run,
    confirm_real_post,
):
    assert dry_run is True
    assert confirm_real_post is False

    attempted.append(
        row["queue_id"]
    )

    return {
        "status": "DRY_RUN",
        "queue_id": row["queue_id"],
    }


pipeline.process_one = process_one

result = pipeline.dispatch_ready(
    object(),
    "night_scout",
    slot_id,
    dry_run=True,
    queue_id="q-exact",
)

assert result["status"] == "DRY_RUN"

assert result["selected_queue_id"] == "q-exact"

assert attempted == [
    "q-exact",
]

missing = pipeline.dispatch_ready(
    object(),
    "night_scout",
    slot_id,
    dry_run=True,
    queue_id="q-missing",
)

assert missing["status"] == "NO_POST"

assert missing["reason"] == (
    "REQUESTED_QUEUE_NOT_READY"
)

source = (
    ROOT
    .joinpath(
        "scripts/"
        "run_direct_reference_media_pipeline.py"
    )
    .read_text(
        encoding="utf-8",
    )
)

assert (
    'parser.add_argument(\n'
    '        "--queue-id",'
    in source
)

assert (
    "queue_id=args.queue_id"
    in source
)

for workflow_name in (
    "direct-reference-media-night-scout.yml",
    "direct-reference-media-liver-manager.yml",
):
    workflow = (
        ROOT
        .joinpath(
            ".github/workflows",
            workflow_name,
        )
        .read_text(
            encoding="utf-8",
        )
    )

    assert "      queue_id:" in workflow

    assert (
        '--queue-id '
        '"${{ github.event.inputs.queue_id }}"'
        in workflow
    )

print(
    "PASS: exact queue bypasses earlier READY rows"
)
print(
    "PASS: missing exact queue fails closed"
)
print(
    "PASS: CLI and both workflows expose exact queue"
)
