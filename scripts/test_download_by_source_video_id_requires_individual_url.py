#!/usr/bin/env python3
import argparse
import json
import tempfile
from pathlib import Path
from download_approved_media import build_download_plan

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "sv.json"
        path.write_text(json.dumps([{"source_video_id": "sv1", "canonical_video_url": "https://youtube.com/channel/abc", "rights_status": "approved_creator_clip"}]), encoding="utf-8")
        args = argparse.Namespace(source_video_id="sv1", source_videos_json=str(path), source_url="", rights_status="approved_creator_clip", download=False, confirm_download=False)
        p = build_download_plan(args)
    ok = "individual_video_url_required" in p["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} download by source_video_id requires individual url")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
