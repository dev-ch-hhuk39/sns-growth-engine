#!/usr/bin/env python3
from argparse import Namespace
import cut_approved_clips as c

def main() -> int:
    plan = c.build_plan(Namespace(input_path="x.mp4", rights_status="third_party_reference_only", dry_run=True, cut=False, confirm_cut=False, vertical=True, burn_subtitles=False, start_seconds=10, end_seconds=35))
    ok = plan["status"] == "BLOCKED" and plan["rights_decision"]["allowed"] is False
    print(f"  {'PASS' if ok else 'FAIL'} cut blocks third party reference only")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
