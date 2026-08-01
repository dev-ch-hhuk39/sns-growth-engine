#!/usr/bin/env python3
"""Regression coverage for content-addressed direct-media assets."""

from ingest_direct_reference_media import (
    _media_asset_contract_issues,
)


DIGEST = "a" * 64

expected = {
    "media_id": f"ma_{DIGEST[:24]}",
    "account_id": "night_scout",
    "source_platform": "threads",
    "reference_post_id": "sp_1",
    "source_post_url": (
        "https://www.threads.com/@source/post/1"
    ),
    "original_media_url": (
        "https://cdn.example.test/image.jpg"
    ),
    "storage_url": (
        "https://res.cloudinary.com/example/"
        "image/upload/v1/x.jpg"
    ),
    "cloudinary_public_id": (
        f"sns-growth/direct/{DIGEST}"
    ),
    "storage_provider": "cloudinary",
    "media_type": "image",
    "mime_type": "image/jpeg",
    "upload_status": "UPLOADED",
    "content_hash": DIGEST,
}

complete = dict(expected)

missing, conflicting = (
    _media_asset_contract_issues(
        complete,
        expected,
    )
)

assert not missing
assert not conflicting

partial_provenance = dict(expected)
partial_provenance["reference_post_id"] = ""

missing, conflicting = (
    _media_asset_contract_issues(
        partial_provenance,
        expected,
    )
)

assert missing == [
    "reference_post_id",
]
assert not conflicting

different_parent = dict(expected)
different_parent["reference_post_id"] = "sp_other"
different_parent["source_post_url"] = (
    "https://www.threads.com/@source/post/other"
)
different_parent["original_media_url"] = (
    "https://cdn.example.test/same-image-alias.jpg"
)

missing, conflicting = (
    _media_asset_contract_issues(
        different_parent,
        expected,
    )
)

assert not missing
assert not conflicting

wrong_account = dict(expected)
wrong_account["account_id"] = "liver_manager"

missing, conflicting = (
    _media_asset_contract_issues(
        wrong_account,
        expected,
    )
)

assert not missing
assert conflicting == [
    "account_id",
]

wrong_storage = dict(expected)
wrong_storage["storage_url"] = (
    "https://res.cloudinary.com/example/"
    "image/upload/v1/different.jpg"
)

missing, conflicting = (
    _media_asset_contract_issues(
        wrong_storage,
        expected,
    )
)

assert not missing
assert conflicting == [
    "storage_url",
]

wrong_hash = dict(expected)
wrong_hash["content_hash"] = "b" * 64

missing, conflicting = (
    _media_asset_contract_issues(
        wrong_hash,
        expected,
    )
)

assert not missing
assert conflicting == [
    "content_hash",
]

missing_identity = dict(expected)
missing_identity["mime_type"] = ""
missing_identity["content_hash"] = ""

missing, conflicting = (
    _media_asset_contract_issues(
        missing_identity,
        expected,
    )
)

assert missing == [
    "mime_type",
    "content_hash",
]
assert not conflicting

print(
    "PASS "
    "test_media_asset_contract.py"
)
