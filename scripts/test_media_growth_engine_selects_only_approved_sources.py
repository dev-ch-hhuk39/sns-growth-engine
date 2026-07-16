#!/usr/bin/env python3
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    plan = build_media_growth_plan("liver_manager")
    ok = len(plan["selected_sources"]) == 5 and all(s["rights_status"] == "approved_creator_clip" for s in plan["selected_sources"])
    print(f"  {'PASS' if ok else 'FAIL'} media growth selects only approved sources")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
