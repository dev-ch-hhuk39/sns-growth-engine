#!/usr/bin/env python3
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    plan = build_media_growth_plan("liver_manager")
    ok = plan["clip_candidate_count"] > 0 and plan["top_clip_candidates"]
    print(f"  {'PASS' if ok else 'FAIL'} media growth generates clip candidates")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
