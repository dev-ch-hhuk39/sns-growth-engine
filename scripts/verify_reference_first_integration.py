#!/usr/bin/env python3
"""Verify the dual-account Reference-first pipeline without external writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.models import (  # noqa: E402
    NormalizedMediaItem,
    NormalizedSourcePost,
    validate_source_post,
)
from generation.reference_first_router import choose_reference_first_route  # noqa: E402
from media.permission_ledger import evaluate_permission  # noqa: E402
from process_threads_queue import ELIGIBLE_STATUSES  # noqa: E402
from public_post_quality import (  # noqa: E402
    final_public_post_validator,
    generate_production_post,
)

ACCOUNTS = ("night_scout", "liver_manager")


def _permission(source_id: str, account_id: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "account_id": account_id,
        "allowed_accounts": [account_id],
        "permission_status": "approved",
        "rights_status": "approved_creator_clip",
        "usage_mode": "direct_and_clip",
        "allow_download": True,
        "allow_cloudinary_storage": True,
        "allow_original_repost": True,
        "allow_new_caption": True,
        "allow_cut": True,
        "allow_clip_repost": True,
        "evidence_type": "integration_fixture",
        "evidence_reference": f"local-contract:{source_id}",
        "approved_by": "test_contract",
        "approved_at": "2026-08-11T00:00:00+00:00",
        "revoked": False,
    }


def verify_account(account_id: str) -> dict[str, Any]:
    if account_id not in ACCOUNTS:
        raise ValueError(f"unsupported account_id: {account_id}")
    source_id = f"integration_{account_id}_youtube"
    post_id = f"sp_{source_id}_video001"
    post_url = "https://www.youtube.com/watch?v=integration001"
    media = NormalizedMediaItem(
        source_post_media_id=f"spm_{post_id}_0",
        source_post_id=post_id,
        media_index=0,
        media_type="video",
        canonical_post_url=post_url,
        original_media_url="https://media.example.invalid/integration001.mp4",
        resolver_backend="yt_dlp",
        mime_type="video/mp4",
        width="1920",
        height="1080",
        duration_seconds="60",
    )
    post = NormalizedSourcePost(
        source_post_id=post_id,
        source_id=source_id,
        target_account_id=account_id,
        platform="youtube",
        profile_url="https://www.youtube.com/channel/integration",
        canonical_post_url=post_url,
        external_post_id="integration001",
        original_post_text=(
            "時給だけでなく控除と続けやすさを確認する店選び"
            if account_id == "night_scout"
            else "初見が入りやすい挨拶とコメントの入口を作る配信設計"
        ),
        published_at="2026-08-11T00:00:00+00:00",
        author_handle="integration_owner",
        media_items=(media,),
        collection_backend="yt_dlp",
        backend_version="contract",
        content_hash=f"hash-{account_id}",
        discovered_at="2026-08-11T00:00:00+00:00",
        detail_status="COMPLETE",
    )
    source_errors = validate_source_post(post)
    permission = evaluate_permission(
        [_permission(source_id, account_id)],
        source_id,
        account_id=account_id,
        required_flags=(
            "allow_download",
            "allow_cloudinary_storage",
            "allow_original_repost",
            "allow_new_caption",
            "allow_cut",
            "allow_clip_repost",
        ),
    )
    understanding = {
        "status": "PASS",
        "transcript_status": "AVAILABLE",
        "standalone_segment_confirmed": True,
        "standalone_story_score": 92,
        "clip_worthy": True,
    }
    direct_route = choose_reference_first_route(
        desired_route="direct_reference_media",
        source_has_direct_media_permission=bool(permission["allowed"]),
        content_understanding=understanding,
    )
    clip_route = choose_reference_first_route(
        desired_route="approved_source_clip",
        source_has_direct_media_permission=bool(permission["allowed"]),
        content_understanding=understanding,
    )
    reference_route = choose_reference_first_route(
        desired_route="reference_text_generation",
        source_has_direct_media_permission=False,
        has_reference_post=True,
    )
    generated = generate_production_post(
        account_id,
        batch_id="reference-first-integration",
        content_type="reference_text_generation",
        reference_signal=post.original_post_text,
    )
    public_text = str(generated.get("public_post_text", ""))
    public_validation = final_public_post_validator(public_text, account_id)
    queue = {
        "queue_id": f"q_integration_{account_id}",
        "account_id": account_id,
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "auto_publish": "false",
        "public_post_text": public_text,
        "source_post_id": post.source_post_id,
        "source_post_media_id": media.source_post_media_id,
    }
    geometry = media.to_sheet_row(
        rights_status="approved_creator_clip",
        permission_status="approved",
    ).get("aspect_ratio")
    checks = {
        "source_identity": not source_errors,
        "provenance": post.author_handle == "integration_owner" and post.collection_backend == "yt_dlp",
        "exact_parent_attachment": media.source_post_id == post.source_post_id and media.canonical_post_url == post.canonical_post_url,
        "content_understanding": understanding["status"] == "PASS",
        "direct_route_selection": direct_route.get("status") == "PASS" and direct_route.get("route") == "direct_reference_media",
        "clip_route_selection": clip_route.get("status") == "PASS" and clip_route.get("route") == "approved_source_clip",
        "reference_route_selection": reference_route.get("status") == "PASS" and reference_route.get("route") == "reference_text_generation",
        "persona_generation": generated.get("validator_result") == "PASS",
        "public_text_validation": public_validation.get("status") == "PASS",
        "waiting_review_contract": queue["status"] == "WAITING_REVIEW" and queue["status"] not in ELIGIBLE_STATUSES and queue["auto_publish"] == "false",
        "source_geometry_preserved": geometry == "16:9",
        "permission_contract": bool(permission["allowed"]),
    }
    return {
        "account_id": account_id,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "source_post_id": post.source_post_id,
        "source_post_media_id": media.source_post_media_id,
        "aspect_ratio": geometry,
        "queue_status": queue["status"],
        "publisher_eligible": queue["status"] in ELIGIBLE_STATUSES,
        "external_calls": False,
        "production_writes": False,
    }


def verify_all() -> dict[str, Any]:
    accounts = {account_id: verify_account(account_id) for account_id in ACCOUNTS}
    return {
        "status": "PASS" if all(row["status"] == "PASS" for row in accounts.values()) else "FAIL",
        "accounts": accounts,
        "external_calls": False,
        "production_writes": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_all()
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text if args.json else f"reference_first_integration={result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
