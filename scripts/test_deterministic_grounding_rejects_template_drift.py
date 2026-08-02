#!/usr/bin/env python3
"""Reject generic advice unsupported by an exact clip transcript."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from acquisition.models import SourcePostBundle
from generation.source_grounded_caption import (
    DeterministicGroundedProvider,
)


SOURCE = (
    "でそういうところで投げても、"
    "すごいと思うかもしれないけど、"
    "楽しくないと思うね。"
)

post = SourcePostBundle(
    source_post_id="sp_false_positive",
    source_id="source_false_positive",
    target_account_id="liver_manager",
    platform="tiktok",
    profile_url=(
        "https://www.tiktok.com/@allowed"
    ),
    canonical_post_url=(
        "https://www.tiktok.com/"
        "@allowed/video/7657837310339222792"
    ),
    external_post_id=(
        "7657837310339222792"
    ),
    original_post_text=SOURCE,
    published_at="",
)

result = DeterministicGroundedProvider().generate(
    post,
    account_id="liver_manager",
    recent_posts=[],
    transcript_excerpt=SOURCE,
)

checks = [
    (
        "generic deterministic drift is rejected",
        result.status != "PASS",
    ),
    (
        "provider fails closed",
        result.status
        in {
            "BLOCKED",
            "UNAVAILABLE",
        },
    ),
]

for name, ok in checks:
    print(
        f"  {'PASS' if ok else 'FAIL'} {name}"
    )

failed = [
    name
    for name, ok in checks
    if not ok
]

print(
    f"PASS: {len(checks) - len(failed)} "
    f"/ FAIL: {len(failed)}"
)

raise SystemExit(
    1 if failed else 0
)
