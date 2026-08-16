#!/usr/bin/env python3
"""Approved clips require exact transcript and persisted AV evidence."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from media.media_probe import (
    asset_has_video_evidence,
)
from media_post_validator import (
    validate_media_post,
)
from run_media_production_pipeline import (
    _build_final_caption_bundle,
    select_candidate,
    select_saved_media_candidate,
)
from test_media_post_validator_requires_approved_rights import GOOD_TEXT


TEXT = GOOD_TEXT

CLIP = {
    "clip_candidate_id": "clip_av_contract",
    "source_video_id": "sv_av_contract",
    "account_id": "liver_manager",
    "clip_status": "MEDIA_READY",
    "reviewer_status": "MEDIA_READY",
    "cut_status": "DONE",
    "upload_status": "UPLOADED",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "transcript_grounded": "TRUE",
    "content_understanding_status": "PASS",
    "transcript_status": "PASS",
    "standalone_segment_confirmed": True,
    "standalone_story_score": 90,
    "clip_worthy": True,
    "transcript_excerpt": TEXT,
    "start_seconds": "10",
    "end_seconds": "30",
    "duration_seconds": "20",
}

SOURCE = {
    "source_video_id": "sv_av_contract",
    "source_id": "src_av_contract",
    "account_id": "liver_manager",
    "platform": "youtube",
    "canonical_video_url": (
        "https://www.youtube.com/"
        "watch?v=abcdefghijk"
    ),
    "title": "親動画の別テーマ",
    "description_preview": "親動画全体の説明",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}

INVALID_ASSET = {
    "media_id": "ma_clip_av_contract",
    "video_clip_id": "clip_av_contract",
    "account_id": "liver_manager",
    "upload_status": "UPLOADED",
    "storage_url": (
        "https://res.cloudinary.com/example/"
        "video/upload/clip.mp4"
    ),
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "duration_seconds": "20",
    "aspect_ratio": "9:16",
}

VALID_ASSET = {
    **INVALID_ASSET,
    "width": "1080",
    "height": "1920",
    "video_stream_count": "1",
    "audio_stream_count": "1",
    "media_probe_status": "PASS",
}


def check(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)

    print(f"  PASS {message}")


def main() -> int:
    bundle, excerpt, reasons = (
        _build_final_caption_bundle(
            clip=CLIP,
            source_video=SOURCE,
            account_id="liver_manager",
            media_asset=VALID_ASSET,
        )
    )

    check(
        bundle is not None and not reasons,
        "exact clip bundle is created",
    )

    check(
        bundle.original_post_text == TEXT,
        "clip transcript is the primary text",
    )

    check(
        SOURCE["title"]
        not in bundle.original_post_text,
        "parent title is excluded from caption evidence",
    )

    check(
        excerpt == TEXT,
        "exact selected transcript is retained",
    )

    check(
        not asset_has_video_evidence(
            INVALID_ASSET
        ),
        "legacy unprobed asset is rejected",
    )

    check(
        asset_has_video_evidence(
            VALID_ASSET
        ),
        "probed AV asset is accepted",
    )

    selected, _, _, invalid_reasons = (
        select_saved_media_candidate(
            [CLIP],
            [SOURCE],
            [INVALID_ASSET],
            [],
            "liver_manager",
        )
    )

    check(
        selected is None,
        "audio-only or unprobed saved asset is skipped",
    )

    check(
        any(
            reason.endswith(
                ":media_stream_evidence_missing"
            )
            for reason in invalid_reasons
        ),
        "saved-asset stream failure is auditable",
    )

    selected, _, selected_asset, reasons = (
        select_saved_media_candidate(
            [CLIP],
            [SOURCE],
            [VALID_ASSET],
            [],
            "liver_manager",
        )
    )

    check(
        selected is not None
        and selected_asset is not None
        and not reasons,
        "verified saved asset remains eligible",
    )

    repair_clip, _, repair_reasons = (
        select_candidate(
            [CLIP],
            [SOURCE],
            [],
            "liver_manager",
            [INVALID_ASSET],
        )
    )

    check(
        repair_clip is not None,
        "invalid MEDIA_READY asset can be regenerated",
    )

    check(
        not any(
            "already_prepared" in reason
            for reason in repair_reasons
        ),
        "invalid asset does not block regeneration",
    )

    base_validation = {
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_url": VALID_ASSET["storage_url"],
        "media_asset_id": VALID_ASSET["media_id"],
        "platform": "threads",
        "account_id": "liver_manager",
        "media_type": "video",
        "media_origin": "approved_source_clip",
        "duration_seconds": 20,
        "aspect_ratio": "9:16",
        "public_post_text": TEXT,
        "alignment_status": "PASS",
        "final_alignment_score": 0.9,
        "main_claim_coverage": 1,
        "unsupported_claim_count": 0,
        "source_copy_similarity": 0.3,
        "recent_post_similarity": 0.2,
        "enforce_video_stream_evidence": True,
    }

    blocked = validate_media_post({
        **base_validation,
        **INVALID_ASSET,
    })

    passed = validate_media_post({
        **base_validation,
        **VALID_ASSET,
    })

    check(
        "media_stream_evidence_missing"
        in blocked["blocked_reasons"],
        "final validator blocks missing AV evidence",
    )

    check(
        passed["status"] == "PASS",
        "final validator accepts verified AV evidence",
    )

    cut_source = (
        ROOT
        / "scripts/cut_approved_clips.py"
    ).read_text(encoding="utf-8")

    upload_source = (
        ROOT
        / "scripts/upload_media_assets.py"
    ).read_text(encoding="utf-8")

    download_source = (
        ROOT
        / "scripts/download_approved_media.py"
    ).read_text(encoding="utf-8")

    check(
        (
            "media_probe = probe_video_file("
            in cut_source
            and "output_path"
            in cut_source
        ),
        "cut output is probed",
    )

    check(
        "media_probe = probe_video_file("
        in upload_source,
        "local file is probed before upload",
    )

    check(
        "downloaded_media_missing_av_streams"
        in download_source,
        "download rejects missing AV streams",
    )

    print(
        "PASS "
        "test_video_stream_evidence_contract.py"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
