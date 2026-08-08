#!/usr/bin/env python3
"""Resolve one canonical video_clip_candidate and physically cut it. Default PLAN_ONLY."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config_partial
from generation.video_clip_materializer import materialize_clip, parse_timecode, validate_bounds
from sheets_client import make_client
from sheets_record_reader import read_records_safely


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--clip-id", required=True)
    parser.add_argument("--output-dir", default="/tmp/sns-growth-engine-clips")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-cut", action="store_true")
    args = parser.parse_args()
    cfg = get_config_partial()
    client = make_client(cfg, dry_run=True, force_mock=False)
    candidates = [
        dict(row) for row in read_records_safely(client, "video_clip_candidates")
        if str(row.get("account_id", "")) == args.account_id
        and str(row.get("clip_id") or row.get("clip_candidate_id") or "") == args.clip_id
    ]
    if len(candidates) != 1:
        print(f"STATUS=BLOCKED_CANDIDATE_MATCH_COUNT_{len(candidates)}")
        return 2
    candidate = candidates[0]
    if str(candidate.get("rights_status", "unknown")).lower() == "not_allowed":
        print("STATUS=BLOCKED_RIGHTS_NOT_ALLOWED")
        return 2
    if str(candidate.get("media_reuse_risk", "low")).lower() == "high":
        print("STATUS=BLOCKED_MEDIA_REUSE_RISK_HIGH")
        return 2
    source_video_id = str(candidate.get("source_video_id", "")).strip()
    videos = [
        dict(row) for row in read_records_safely(client, "source_videos")
        if str(row.get("account_id", "")) == args.account_id
        and str(row.get("source_video_id", "")) == source_video_id
    ]
    if len(videos) != 1:
        print(f"STATUS=BLOCKED_SOURCE_VIDEO_MATCH_COUNT_{len(videos)}")
        return 2
    source = videos[0]
    input_path = Path(str(source.get("local_path", ""))).expanduser()
    start = parse_timecode(candidate.get("start_seconds") or candidate.get("start_time"))
    end = parse_timecode(candidate.get("end_seconds") or candidate.get("end_time"))
    duration = validate_bounds(start, end)
    print(f"clip_id={args.clip_id}")
    print(f"source_video_id_present={'true' if source_video_id else 'false'}")
    print(f"source_local_file_present={'true' if input_path.is_file() else 'false'}")
    print(f"duration_seconds={duration:.3f}")
    print("sheet_writes_performed=false")
    print("cloudinary_uploads_performed=false")
    print("posts_performed=false")
    if not input_path.is_file():
        print("STATUS=BLOCKED_LOCAL_SOURCE_VIDEO_MISSING")
        return 3
    if not (args.apply and args.confirm_cut):
        print("STATUS=PLAN_ONLY_READY_TO_CUT")
        return 0
    output = Path(args.output_dir) / f"{args.clip_id}.mp4"
    result = materialize_clip(input_path, output, start, end)
    print(f"output_exists={'true' if Path(result['output_path']).is_file() else 'false'}")
    print(f"actual_duration_seconds={result['actual_duration_seconds']:.3f}")
    print(f"size_bytes={result['size_bytes']}")
    print("STATUS=MATERIALIZED_LOCAL_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
