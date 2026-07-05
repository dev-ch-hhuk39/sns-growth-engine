#!/usr/bin/env python3
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    p = build_media_growth_plan("liver_manager")
    ok = p["top_clip_candidates"] and all(c["public_post_validator_status"] == "PASS" for c in p["top_clip_candidates"])
    print(f"  {'PASS' if ok else 'FAIL'} clip candidate public post validator pass")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
