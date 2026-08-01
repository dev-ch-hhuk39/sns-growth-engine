#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import ingest_direct_reference_media as module


DIGEST = (
    "d4b16aa45189ad1017d90b7ed3b67ea3"
    "0da1c24f118ee4f1d8c2ef4eb2d62095"
)

ASSET_ID = f"ma_{DIGEST[:24]}"

PUBLIC_ID = f"sns-growth/direct/{DIGEST}"

STORAGE_URL = (
    "https://res.cloudinary.com/example/image/upload/"
    f"{PUBLIC_ID}.jpg"
)

expected = {
    "media_id": ASSET_ID,
    "account_id": "night_scout",
    "source_platform": "threads",
    "reference_post_id": "post-new",
    "source_post_url": (
        "https://www.threads.com/@sample/post/new"
    ),
    "original_media_url": (
        "https://cdninstagram.com/new.jpg"
    ),
    "storage_url": STORAGE_URL,
    "cloudinary_public_id": PUBLIC_ID,
    "storage_provider": "cloudinary",
    "media_type": "image",
    "mime_type": "image/jpeg",
    "upload_status": "UPLOADED",
    "content_hash": DIGEST,
}

existing = {
    **expected,
    "reference_post_id": "post-first",
    "source_post_url": (
        "https://www.threads.com/@sample/post/first"
    ),
    "original_media_url": (
        "https://cdninstagram.com/first.jpg"
    ),
    "content_hash": "",
}

missing, conflicting = (
    module._media_asset_contract_issues(
        existing,
        expected,
    )
)

assert missing == [
    "content_hash",
]

assert conflicting == []

filled = {
    **existing,
    "content_hash": DIGEST,
}

missing, conflicting = (
    module._media_asset_contract_issues(
        filled,
        expected,
    )
)

assert missing == []
assert conflicting == []

cross_account = {
    **filled,
    "account_id": "liver_manager",
}

_missing, conflicting = (
    module._media_asset_contract_issues(
        cross_account,
        expected,
    )
)

assert "account_id" in conflicting

different_storage = {
    **filled,
    "storage_url": (
        "https://res.cloudinary.com/example/"
        "image/upload/different.jpg"
    ),
}

_missing, conflicting = (
    module._media_asset_contract_issues(
        different_storage,
        expected,
    )
)

assert "storage_url" in conflicting

post = {
    "target_account_id": "night_scout",
    "platform": "threads",
}

media = {
    "media_type": "image",
}

reusable_existing = {
    **filled,
    "content_hash": "",
}

issues = (
    module._reusable_identical_asset_issues(
        reusable_existing,
        post,
        media,
        DIGEST,
    )
)

assert issues == []

issues = (
    module._reusable_identical_asset_issues(
        {
            **reusable_existing,
            "account_id": "liver_manager",
        },
        post,
        media,
        DIGEST,
    )
)

assert "account_id" in issues

issues = (
    module._reusable_identical_asset_issues(
        {
            **reusable_existing,
            "cloudinary_public_id": (
                "sns-growth/direct/"
                + ("0" * 64)
            ),
        },
        post,
        media,
        DIGEST,
    )
)

assert "cloudinary_public_id" in issues
assert "content_hash" in issues

assert (
    module._safe_ingest_error_code(
        RuntimeError(
            "media_asset_contract_conflict:"
            "reference_post_id"
        )
    )
    == "media_asset_contract_conflict"
)

assert (
    module._safe_ingest_error_code(
        RuntimeError(
            "provider response contained private detail"
        )
    )
    == "RuntimeError"
)

assert (
    module._safe_ingest_error_code(
        ValueError(
            "private detail"
        )
    )
    == "ValueError"
)

print(
    "PASS "
    "test_direct_media_identical_content_reuse.py"
)
