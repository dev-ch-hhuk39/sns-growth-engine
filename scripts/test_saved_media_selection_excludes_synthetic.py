#!/usr/bin/env python3
"""Regression: saved clip selection must reject synthetic legacy assets."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from run_media_production_pipeline import select_saved_media_candidate


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  PASS {message}")


def main() -> int:
    account_id = "night_scout"

    synthetic_clip = {
        "clip_candidate_id": "clip_system_owned_old_generated_clip",
        "source_video_id": "video_system_owned_old_generated_clip",
        "account_id": account_id,
        "clip_status": "READY",
        "rights_status": "owned",
        "permission_status": "approved",
        "transcript_grounded": "TRUE",
        "transcript_excerpt": "synthetic legacy transcript",
        "start_seconds": "0",
        "end_seconds": "8",
    }

    approved_clip = {
        "clip_candidate_id": "clipcand_approved_creator_01",
        "source_video_id": "sv_approved_creator_01",
        "account_id": account_id,
        "clip_status": "MEDIA_READY",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "transcript_grounded": "TRUE",
        "transcript_excerpt": (
            "配信前に最初の話題を決めておくと、"
            "コメントがない時間も進行しやすい。"
        ),
        "start_seconds": "15",
        "end_seconds": "42",
        "confidence_score": "92",
    }

    ungrounded_clip = {
        "clip_candidate_id": "clipcand_ungrounded_01",
        "source_video_id": "sv_ungrounded_01",
        "account_id": account_id,
        "clip_status": "MEDIA_READY",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "transcript_grounded": "FALSE",
        "transcript_excerpt": "",
        "start_seconds": "10",
        "end_seconds": "30",
    }

    source_videos = [
        {
            "source_video_id": "video_system_owned_old_generated_clip",
            "account_id": account_id,
            "platform": "system_generated_owned",
            "canonical_video_url": "",
            "rights_status": "owned",
            "permission_status": "approved",
        },
        {
            "source_video_id": "sv_approved_creator_01",
            "source_id": "src_ns_yt_cand_001",
            "account_id": account_id,
            "platform": "youtube",
            "canonical_video_url": (
                "https://www.youtube.com/watch?v=8Xmkojfw90Q"
            ),
            "rights_status": "approved_creator_clip",
            "permission_status": "approved",
            "title": "初心者向け配信の進め方",
        },
        {
            "source_video_id": "sv_ungrounded_01",
            "source_id": "src_ns_yt_cand_002",
            "account_id": account_id,
            "platform": "youtube",
            "canonical_video_url": (
                "https://www.youtube.com/watch?v=abcdefghijk"
            ),
            "rights_status": "approved_creator_clip",
            "permission_status": "approved",
        },
    ]

    media_assets = [
        {
            "media_id": "ma_system_owned_old_generated_clip",
            "video_clip_id": (
                "clip_system_owned_old_generated_clip"
            ),
            "account_id": account_id,
            "upload_status": "UPLOADED",
            "storage_url": (
                "https://example.invalid/synthetic.mp4"
            ),
            "rights_status": "owned",
            "permission_status": "approved",
            "media_origin": "system_generated_owned",
            "source_platform": "system_generated_owned",
            "provider_name": "pillow+ffmpeg",
            "created_at": "2026-07-01T00:00:00+00:00",
        },
        {
            "media_id": "ma_clipcand_ungrounded_01",
            "video_clip_id": "clipcand_ungrounded_01",
            "account_id": account_id,
            "upload_status": "UPLOADED",
            "storage_url": (
                "https://example.invalid/ungrounded.mp4"
            ),
            "rights_status": "approved_creator_clip",
            "permission_status": "approved",
            "media_origin": "approved_source_clip",
            "created_at": "2026-07-02T00:00:00+00:00",
        },
        {
            "media_id": "ma_clipcand_approved_creator_01",
            "video_clip_id": "clipcand_approved_creator_01",
            "account_id": account_id,
            "upload_status": "UPLOADED",
            "storage_url": (
                "https://example.invalid/approved.mp4"
            ),
            "rights_status": "approved_creator_clip",
            "permission_status": "approved",
            "media_origin": "approved_source_clip",
            "duration_seconds": "27",
            "width": "1080",
            "height": "1920",
            "video_stream_count": "1",
            "audio_stream_count": "1",
            "media_probe_status": "PASS",
            "created_at": "2026-07-03T00:00:00+00:00",
        },
    ]

    selected_clip, selected_video, selected_asset, reasons = (
        select_saved_media_candidate(
            [
                synthetic_clip,
                approved_clip,
                ungrounded_clip,
            ],
            source_videos,
            media_assets,
            [],
            account_id,
        )
    )

    check(
        selected_clip is not None,
        "an eligible approved-source clip is selected",
    )
    check(
        selected_clip["clip_candidate_id"]
        == "clipcand_approved_creator_01",
        "synthetic and ungrounded clips are skipped",
    )
    check(
        selected_video["source_video_id"]
        == "sv_approved_creator_01",
        "selected clip keeps its exact source video",
    )
    check(
        selected_asset["media_id"]
        == "ma_clipcand_approved_creator_01",
        "selected asset is the approved uploaded clip",
    )
    check(
        any(
            reason.endswith(
                ":synthetic_media_forbidden"
            )
            for reason in reasons
        ),
        "synthetic rejection is auditable",
    )
    check(
        any(
            reason.endswith(
                ":transcript_grounding_required"
            )
            for reason in reasons
        ),
        "missing transcript grounding is auditable",
    )

    print(
        "PASS "
        "test_saved_media_selection_excludes_synthetic.py"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
