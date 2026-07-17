#!/usr/bin/env python3
"""Health inventory reports safe per-account media counts without content."""
from __future__ import annotations

from check_autonomous_health import _media_asset_inventory


rows = [
    {
        "media_id": "ma_ns_1",
        "account_id": "night_scout",
        "video_clip_id": "clip_ns_1",
        "upload_status": "UPLOADED",
        "storage_url": "https://media.example.invalid/ns1.mp4",
    },
    {
        "media_id": "ma_ns_2",
        "account_id": "night_scout",
        "clip_candidate_id": "clip_ns_2",
        "upload_status": "UPLOADED",
        "storage_url": "https://media.example.invalid/ns2.mp4",
    },
    {
        "media_id": "ma_lm_clip",
        "account_id": "liver_manager",
        "video_clip_id": "clip_lm_1",
        "upload_status": "UPLOADED",
        "storage_url": "https://media.example.invalid/lm1.mp4",
    },
    {
        "media_id": "ma_lm_direct",
        "account_id": "liver_manager",
        "reference_post_id": "sp_lm_1",
        "upload_status": "UPLOADED",
        "storage_url": "https://media.example.invalid/lm-direct.mp4",
    },
]
inventory = _media_asset_inventory(rows)
checks = [
    ("all accounts counted", inventory["account_counts"] == {"liver_manager": 2, "night_scout": 2}),
    ("generated clips counted", inventory["generated_clip_asset_count"] == 3),
    ("generated clips grouped", inventory["generated_clip_account_counts"] == {"liver_manager": 1, "night_scout": 2}),
    ("direct assets counted", inventory["direct_reference_asset_count"] == 1),
    ("uploaded assets counted", inventory["uploaded_asset_count"] == 4),
    ("no media URLs exposed", not any("url" in key for key in inventory)),
]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
failed = [name for name, passed in checks if not passed]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
