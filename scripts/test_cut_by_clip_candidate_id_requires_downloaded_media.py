#!/usr/bin/env python3
import argparse
import json
import tempfile
from pathlib import Path
from cut_approved_clips import build_plan

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "clips.json"
        path.write_text(json.dumps([{"clip_candidate_id": "c1", "rights_status": "approved_creator_clip", "start_seconds": 1, "end_seconds": 10, "cut_status": "NOT_CUT"}]), encoding="utf-8")
        args = argparse.Namespace(input_path="", clip_candidate_id="c1", clip_candidates_json=str(path), rights_status="approved_creator_clip", dry_run=True, cut=False, confirm_cut=False, start_seconds=0, end_seconds=0, vertical=True, burn_subtitles=False)
        p = build_plan(args)
    ok = "downloaded_media_required" in p["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} cut by clip_candidate_id requires downloaded media")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
