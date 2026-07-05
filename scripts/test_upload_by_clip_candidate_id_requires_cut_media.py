#!/usr/bin/env python3
import argparse
import json
import tempfile
from pathlib import Path
from upload_media_assets import _asset_from_clip_candidate, build_upload_plan

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "clips.json"
        path.write_text(json.dumps([{"clip_candidate_id": "c1", "rights_status": "approved_creator_clip", "cut_status": "NOT_CUT"}]), encoding="utf-8")
        args = argparse.Namespace(account_id="liver_manager", clip_candidate_id="c1", clip_candidates_json=str(path), media_asset_id="", rights_status="approved_creator_clip", upload=False, confirm_upload=False, dry_run=True)
        asset = _asset_from_clip_candidate(args)
        p = build_upload_plan(args, [asset])
    ok = "cut_media_local_path_required" in p["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} upload by clip_candidate_id requires cut media")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
