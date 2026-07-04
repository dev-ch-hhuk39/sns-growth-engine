#!/usr/bin/env python3
from argparse import Namespace
from download_approved_media import build_download_plan

def main() -> int:
    plan = build_download_plan(Namespace(source_url="https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ", rights_status="approved_creator_clip", dry_run=True, download=True, confirm_download=True))
    ok = plan["status"] == "BLOCKED" and "individual_video_url_required" in plan["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} download blocks channel URL apply")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
