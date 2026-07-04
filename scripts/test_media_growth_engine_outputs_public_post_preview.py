#!/usr/bin/env python3
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    plan = build_media_growth_plan("liver_manager")
    ok = bool(plan["public_post_preview"]) and plan["final_public_post_validator"] == "PASS"
    print(f"  {'PASS' if ok else 'FAIL'} media growth outputs public post preview")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
