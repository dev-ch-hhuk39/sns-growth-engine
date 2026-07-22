#!/usr/bin/env python3
"""Strict caption rejection is a normal no-work result, not a workflow crash."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_growth_test_fixtures import liver_video_and_transcript
from run_media_growth_engine import build_media_growth_plan


class RejectingCaptionService:
    def generate(self, *_args, **_kwargs):
        return {
            "status": "BLOCKED",
            "public_post_text": "",
            "internal_analysis": {},
            "claim_support": [],
            "semantic_alignment": {"status": "BLOCKED"},
            "provider_name": "fixture_rejecting",
            "provider_version": "1",
        }


video, transcript = liver_video_and_transcript()
plan = build_media_growth_plan(
    "liver_manager",
    apply=True,
    confirm_media_growth=True,
    existing_source_videos=[video],
    existing_transcripts=[transcript],
    caption_service=RejectingCaptionService(),
)
checks = [
    ("strictly rejected caption is not promoted", plan["final_public_post_validator"] == "BLOCKED"),
    ("no eligible candidate has explicit reason", plan["no_eligible_reasons"] == ["public_post_validator_blocked"]),
    ("no eligible candidate is not a safety configuration failure", plan["status"] == "NO_ELIGIBLE_CANDIDATE"),
    ("media effects remain disabled in plan", not any(plan[key] for key in ("would_download", "would_cut", "would_upload", "would_post_video"))),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
