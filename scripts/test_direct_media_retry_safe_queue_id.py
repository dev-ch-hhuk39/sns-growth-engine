#!/usr/bin/env python3

from __future__ import annotations

import re
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
        "source_post_id": "sp_source_01",
        "source_id": "source_01",
        "post_url": "https://example.invalid/post",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "content_hash": "source-content-hash",
    },
    "source_post_media": {
        "storage_url": (
            "https://example.invalid/image.jpg"
        ),
        "media_type": "image",
        "duration_seconds": "",
        "aspect_ratio": "1:1",
    },
    "media_asset_id": "media_01",
    "media_asset_ids": [
        "media_01",
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

first = pipeline._build_queue(
    deepcopy(base_plan)
)

second = pipeline._build_queue(
    deepcopy(base_plan)
)

changed_plan = deepcopy(base_plan)

changed_plan["public_post_text"] = (
    "元投稿を別の形で軽く校正した本文です。"
)

changed = pipeline._build_queue(
    changed_plan
)

assert first["queue_id"] == second["queue_id"]

assert first["queue_id"] != changed["queue_id"]

assert first["queue_id"].startswith(
    "direct_media_20260801_"
    "night_scout_sp_source_01_media_01_"
)

suffix = first["queue_id"].rsplit(
    "_",
    1,
)[-1]

assert re.fullmatch(
    r"[0-9a-f]{12}",
    suffix,
)

print(
    "PASS: identical caption/media remains idempotent"
)
print(
    "PASS: changed caption receives a new queue ID"
)
print(
    "PASS: queue identity includes a stable hash"
)
