#!/usr/bin/env python3
import argparse
from download_approved_media import build_download_plan
from cut_approved_clips import build_plan as build_cut_plan

def main() -> int:
    d = build_download_plan(argparse.Namespace(source_video_id="", source_videos_json="", source_url="https://www.youtube.com/watch?v=abc", rights_status="approved_creator_clip", download=True, confirm_download=False))
    c = build_cut_plan(argparse.Namespace(input_path="x.mp4", clip_candidate_id="", clip_candidates_json="", rights_status="approved_creator_clip", dry_run=True, cut=True, confirm_cut=False, start_seconds=1, end_seconds=10, vertical=True, burn_subtitles=False))
    ok = "--download requires --confirm-download" in d["blocked_reasons"] and "--cut requires --confirm-cut" in c["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} download/cut/upload require env confirm")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
