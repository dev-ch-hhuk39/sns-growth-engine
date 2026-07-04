#!/usr/bin/env python3
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    plan = build_media_growth_plan("liver_manager")
    ok = plan["status"] == "PLAN_ONLY" and plan["would_download"] is False and plan["would_post_video"] is False
    print(f"  {'PASS' if ok else 'FAIL'} media growth engine dry-run")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
