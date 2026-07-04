#!/usr/bin/env python3
from argparse import Namespace
import cut_approved_clips as c

def main() -> int:
    plan = c.build_plan(Namespace(input_path="output/downloads/sample.mp4", rights_status="approved_creator_clip", dry_run=True, cut=False, confirm_cut=False, vertical=True, burn_subtitles=True, start_seconds=10, end_seconds=35))
    ok = plan["status"] == "PLAN_ONLY" and plan["vertical_9x16"] is True and plan["burn_subtitles"] is True and plan["would_cut"] is False
    print(f"  {'PASS' if ok else 'FAIL'} cut plan vertical subtitles")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
