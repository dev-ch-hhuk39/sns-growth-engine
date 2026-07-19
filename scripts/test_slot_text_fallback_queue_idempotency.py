#!/usr/bin/env python3
"""A retry must reuse a READY slot fallback row instead of appending it."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_slot_text_fallback as fallback


def main() -> int:
    plan = fallback.build_plan(
        "night_scout",
        "ns_1400_reference",
        "asset_unavailable",
        apply=True,
    )
    queue_id = "slot_fallback_20260719_night_scout_ns_1400_reference_1"
    existing = {
        "queue_id": queue_id,
        "account_id": "night_scout",
        "platform": "threads",
        "status": "READY",
        "public_post_text": plan["public_post_text"],
    }
    appended: list[dict] = []
    processed: list[dict] = []

    original_records = fallback.records
    original_append = fallback.append_row
    original_process = fallback.process_one
    original_upsert = fallback.upsert_slot_run
    try:
        fallback.records = lambda _client, tab: [existing] if tab == "queue" else []
        fallback.append_row = lambda _client, _tab, row: appended.append(dict(row))
        fallback.process_one = lambda _client, row, **_kwargs: (
            processed.append(dict(row)) or {
                "status": "POSTED",
                "result_id": "result-test",
                "post_url": "https://www.threads.com/@example/post/test",
            }
        )
        fallback.upsert_slot_run = lambda *_args, **_kwargs: None
        result = fallback.execute(
            plan,
            object(),
            started={
                "schedule_date_jst": "2026-07-19",
                "slot_run_id": "slot-run-test",
            },
        )
    finally:
        fallback.records = original_records
        fallback.append_row = original_append
        fallback.process_one = original_process
        fallback.upsert_slot_run = original_upsert

    assert not appended, appended
    assert processed and processed[0]["queue_id"] == queue_id, processed
    assert result["status"] == "POSTED", result
    print("PASS test_slot_text_fallback_queue_idempotency.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
