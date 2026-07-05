#!/usr/bin/env python3
from discover_approved_source_videos import build_discovery_plan

def main() -> int:
    p = build_discovery_plan("liver_manager")
    tiktok = [r for r in p["source_results"] if r["platform"] == "tiktok"]
    ok = tiktok and all(r["discovery_status"] == "TIKTOK_ACCOUNT_LIMITED_MANUAL_SAFE_PLAN" and r["discovered_video_count"] <= p["limits"]["max_new_videos_per_source_per_run"] for r in tiktok)
    print(f"  {'PASS' if ok else 'FAIL'} tiktok account discovery limited")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
