#!/usr/bin/env python3
from discover_approved_source_videos import build_discovery_plan

def main() -> int:
    p = build_discovery_plan("liver_manager")
    ok = p["status"] == "PLAN_ONLY" and p["discovery_enabled"] and p["would_save_source_videos"] is False and p["new_video_count"] > 0
    print(f"  {'PASS' if ok else 'FAIL'} discover approved source videos dry-run")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
