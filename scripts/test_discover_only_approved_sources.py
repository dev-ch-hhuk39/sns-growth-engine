#!/usr/bin/env python3
from discover_approved_source_videos import build_discovery_plan

def main() -> int:
    p = build_discovery_plan("liver_manager")
    ok = len(p["selected_sources"]) == 5 and all(r["rights_status"] == "approved_creator_clip" for r in p["source_results"])
    print(f"  {'PASS' if ok else 'FAIL'} discover only approved sources")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
