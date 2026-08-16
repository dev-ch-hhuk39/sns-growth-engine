"""Cuts preserve source orientation unless vertical conversion is explicit."""
from __future__ import annotations

from argparse import Namespace
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import cut_approved_clips as cutter
from media_post_validator import validate_media_post
from test_media_post_validator_requires_approved_rights import GOOD_TEXT


def main() -> int:
    plan = cutter.build_plan(Namespace(
        input_path="sample.mp4", clip_candidate_id="", clip_candidates_json="",
        clip_candidate_row=None, rights_status="approved_creator_clip", dry_run=True,
        cut=False, confirm_cut=False, start_seconds=10, end_seconds=30,
        vertical=False, burn_subtitles=False, source_aspect_ratio="16:9",
    ))
    assert plan["vertical_9x16"] is False
    assert plan["aspect_ratio_policy"] == "preserve_source"
    assert plan["source_aspect_ratio"] == "16:9"

    base = {
        "rights_status": "owned", "permission_status": "approved",
        "media_url": "https://cdn.example/video.mp4", "media_asset_id": "asset_1",
        "platform": "threads", "account_id": "liver_manager", "media_type": "video",
        "content_type": "approved_source_clip", "duration_seconds": 20,
        "aspect_ratio": "16:9", "source_aspect_ratio": "16:9",
        "aspect_ratio_policy": "preserve_source",
        "public_post_text": GOOD_TEXT,
        "alignment_status": "PASS", "final_alignment_score": 0.9,
        "main_claim_coverage": 0.9, "unsupported_claim_count": 0,
        "source_copy_similarity": 0.1, "recent_post_similarity": 0.1,
    }
    assert validate_media_post(base)["status"] == "PASS"
    mismatch = validate_media_post({**base, "aspect_ratio": "9:16"})
    assert "aspect_ratio_not_preserved_from_source" in mismatch["blocked_reasons"]
    print("PASS test_media_aspect_ratio_preservation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
