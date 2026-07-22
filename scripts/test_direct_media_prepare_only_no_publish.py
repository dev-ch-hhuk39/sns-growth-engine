#!/usr/bin/env python3
"""Direct-media preparation may persist READY inventory but never publish."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_direct_reference_media_pipeline as pipeline


plan = {
    "account_id": "night_scout",
    "slot_id": "ns_1800_direct_media",
    "source_post": {
        "source_post_id": "post_1",
        "source_id": "source_1",
        "post_url": "https://www.threads.com/@example/post/1",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "content_hash": "content_1",
    },
    "source_post_media": {
        "storage_url": "https://res.cloudinary.com/demo/image/upload/example.jpg",
        "media_type": "image",
    },
    "media_asset_id": "asset_1",
    "media_asset_ids": ["asset_1"],
    "media_urls": ["https://res.cloudinary.com/demo/image/upload/example.jpg"],
    "media_types": ["image"],
    "public_post_text": "夜職の店選びでは、時給だけでなく客層や相談しやすさも確認すると、自分に合う環境を見つけやすくなります。焦らず条件を整理してから比べることが大切です。",
    "semantic_alignment": {"status": "PASS"},
}


class Client:
    pass


saved: list[dict] = []
published = False
original_records = pipeline._records
original_append = pipeline.append_row
original_process = pipeline.process_one
try:
    pipeline._records = lambda _client, _logical: []
    pipeline.append_row = lambda _client, logical, row: saved.append({"logical": logical, **row})

    def fail_if_published(*_args, **_kwargs):
        global published
        published = True
        raise AssertionError("prepare-only called publisher")

    pipeline.process_one = fail_if_published
    result = pipeline.prepare(plan, Client())
finally:
    pipeline._records = original_records
    pipeline.append_row = original_append
    pipeline.process_one = original_process

checks = [
    ("prepared status", result.get("status") == "PREPARED"),
    ("one READY row saved", len(saved) == 1 and saved[0].get("status") == "READY"),
    ("canonical slot saved", saved[0].get("slot_id") == "ns_1800_direct_media"),
    ("media provenance saved", saved[0].get("media_origin") == "direct_reference"),
    ("publisher never called", not published),
    ("would_post false", result.get("would_post") is False),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
