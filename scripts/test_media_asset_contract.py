#!/usr/bin/env python3
"""Regression coverage for immutable direct-media asset parent contracts."""
from ingest_direct_reference_media import _media_asset_contract_issues

expected = {
    "media_id": "ma_hash",
    "account_id": "night_scout",
    "reference_post_id": "sp_1",
    "source_post_url": "https://www.threads.com/@source/post/1",
    "original_media_url": "https://cdn.example.test/image.jpg",
    "storage_url": "https://res.cloudinary.com/example/image/upload/v1/x.jpg",
    "cloudinary_public_id": "sns-growth/direct/hash",
    "storage_provider": "cloudinary",
    "upload_status": "UPLOADED",
}
complete = dict(expected)
missing, conflicting = _media_asset_contract_issues(complete, expected)
assert not missing and not conflicting, (missing, conflicting)

partial = dict(expected)
partial["reference_post_id"] = ""
missing, conflicting = _media_asset_contract_issues(partial, expected)
assert missing == ["reference_post_id"] and not conflicting, (missing, conflicting)

wrong_parent = dict(expected)
wrong_parent["reference_post_id"] = "sp_other"
missing, conflicting = _media_asset_contract_issues(wrong_parent, expected)
assert not missing and conflicting == ["reference_post_id"], (missing, conflicting)

print("PASS test_media_asset_contract.py")
