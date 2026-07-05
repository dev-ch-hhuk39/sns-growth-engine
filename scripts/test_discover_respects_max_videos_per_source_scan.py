#!/usr/bin/env python3
import discover_approved_source_videos as d

def main() -> int:
    cfg = d.load_config()
    cfg["max_videos_per_source_scan"] = 2
    cfg["max_new_videos_per_source_per_run"] = 10
    original = d.load_config
    d.load_config = lambda: cfg
    try:
        p = d.build_discovery_plan("liver_manager")
    finally:
        d.load_config = original
    ok = all(r["discovered_video_count"] <= 2 for r in p["source_results"])
    print(f"  {'PASS' if ok else 'FAIL'} discover respects max_videos_per_source_scan")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
