#!/usr/bin/env python3

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_direct_reference_media_pipeline as pipeline  # noqa: E402


pipeline.business_date = lambda: "2026-08-01"

base_plan = {
    "account_id": "night_scout",
    "slot_id": "ns_1800_direct_media",
    "source_post": {
        "source_post_id": "sp_source_legacy",
        "source_id": "source_legacy",
        "post_url": (
            "https://example.invalid/post"
        ),
        "rights_status": (
            "approved_creator_clip"
        ),
        "permission_status": "approved",
        "content_hash": "source-hash",
    },
    "source_post_media": {
        "storage_url": (
            "https://example.invalid/image.jpg"
        ),
        "media_type": "image",
        "duration_seconds": "",
        "aspect_ratio": "1:1",
    },
    "media_asset_id": "media_legacy",
    "media_asset_ids": [
        "media_legacy",
    ],
    "media_urls": [
        "https://example.invalid/image.jpg",
    ],
    "media_types": [
        "image",
    ],
    "public_post_text": (
        "元投稿を軽く校正した本文です。"
    ),
    "caption_mode": "source_copyedit",
    "semantic_alignment": {
        "status": "PASS",
        "final_alignment_score": 0.95,
        "main_claim_coverage": 1.0,
        "unsupported_claim_count": 0,
        "source_copy_similarity": 1.0,
        "recent_post_similarity": 0.1,
    },
    "claim_support": [],
}

legacy_row = {
    "queue_id": (
        "direct_media_20260801_"
        "night_scout_"
        "sp_source_legacy_"
        "media_legacy"
    ),
    "account_id": "night_scout",
    "target_account_id": "night_scout",
    "platform": "threads",
    "generation_mode": (
        "direct_reference_media"
    ),
    "business_date_jst": "2026-08-01",
    "source_post_id": "sp_source_legacy",
    "media_asset_id": "media_legacy",
    "media_asset_ids_json": (
        '["media_legacy"]'
    ),
    "public_post_text": (
        "元投稿を軽く校正した本文です。"
    ),
    "status": "READY",
}

rows = [
    dict(legacy_row),
]

appended = []


pipeline._records = (
    lambda _client, logical: (
        [dict(row) for row in rows]
        if logical == "queue"
        else []
    )
)

pipeline.append_row = (
    lambda _client, logical, row: (
        appended.append(
            (
                logical,
                dict(row),
            )
        )
    )
)

pipeline._invalidate_records = (
    lambda *_args, **_kwargs: None
)

same = pipeline.prepare(
    deepcopy(base_plan),
    object(),
)

assert same["already_prepared"] is True

assert same["matched_legacy_queue"] is True

assert (
    same["queue_id"]
    == legacy_row["queue_id"]
)

assert (
    same["generated_queue_id"]
    != legacy_row["queue_id"]
)

assert appended == []

changed_plan = deepcopy(base_plan)

changed_plan["public_post_text"] = (
    "元投稿を別の形で軽く校正した本文です。"
)

changed = pipeline.prepare(
    changed_plan,
    object(),
)

assert changed["already_prepared"] is False

assert changed["matched_legacy_queue"] is False

assert changed["queue_id"].endswith(
    changed["generated_queue_id"].rsplit(
        "_",
        1,
    )[-1]
)

assert len(appended) == 1

assert appended[0][0] == "queue"

assert (
    appended[0][1]["public_post_text"]
    == changed_plan["public_post_text"]
)

print(
    "PASS: identical legacy queue is not duplicated"
)
print(
    "PASS: legacy queue ID remains observable"
)
print(
    "PASS: changed caption creates a new hashed queue"
)
