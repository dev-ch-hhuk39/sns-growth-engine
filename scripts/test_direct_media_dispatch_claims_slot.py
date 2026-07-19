#!/usr/bin/env python3
"""A READY direct-media dispatcher claims its slot before one publish call."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_direct_reference_media_pipeline as pipeline


queue = {
    "queue_id": "queue_1",
    "account_id": "liver_manager",
    "platform": "threads",
    "status": "READY",
    "generation_mode": "direct_reference_media",
    "slot_id": "lm_1600_direct_media",
    "business_date_jst": pipeline.business_date(),
    "source_post_id": "post_1",
    "media_asset_id": "asset_1",
}
events: list[str] = []
original_records = pipeline._records
original_existing = pipeline.existing_slot_status
original_claim = pipeline.claim_slot_run
original_process = pipeline.process_one
original_upsert = pipeline.upsert_slot_run
try:
    pipeline._records = lambda _client, logical: [queue] if logical == "queue" else []
    pipeline.existing_slot_status = lambda *_args, **_kwargs: ""

    def claim(*_args, **_kwargs):
        events.append("claim")
        return {"status": "CLAIMED", "slot_run_id": "slot_1"}

    def publish(*_args, **kwargs):
        if kwargs.get("dry_run"):
            events.append("preflight")
            return {"status": "DRY_RUN"}
        events.append("publish")
        return {"status": "POSTED", "result_id": "result_1", "post_url": "https://www.threads.com/@example/post/1"}

    pipeline.claim_slot_run = claim
    pipeline.process_one = publish
    pipeline.upsert_slot_run = lambda *_args, **_kwargs: {"status": "UPDATED"}
    result = pipeline.dispatch_ready(object(), "liver_manager", "lm_1600_direct_media", dry_run=False)
finally:
    pipeline._records = original_records
    pipeline.existing_slot_status = original_existing
    pipeline.claim_slot_run = original_claim
    pipeline.process_one = original_process
    pipeline.upsert_slot_run = original_upsert

checks = [
    ("posted", result.get("status") == "POSTED"),
    ("preflight and claim precede publish", events == ["preflight", "claim", "publish"]),
    ("one candidate selected", result.get("selected_queue_id") == "queue_1"),
    ("would_post false after execution", result.get("would_post") is False),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
