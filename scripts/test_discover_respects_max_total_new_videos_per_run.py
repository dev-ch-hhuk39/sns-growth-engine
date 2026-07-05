#!/usr/bin/env python3
import discover_approved_source_videos as d

def main() -> int:
    cfg = d.load_config()
    cfg["max_total_new_videos_per_run"] = 3
    original = d.load_config
    d.load_config = lambda: cfg
    try:
        p = d.build_discovery_plan("liver_manager")
    finally:
        d.load_config = original
    ok = p["new_video_count"] <= 3 and p["skipped_video_count"] > 0
    print(f"  {'PASS' if ok else 'FAIL'} discover respects max_total_new_videos_per_run")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
