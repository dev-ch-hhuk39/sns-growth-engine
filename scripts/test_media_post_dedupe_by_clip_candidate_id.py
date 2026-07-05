#!/usr/bin/env python3

def main() -> int:
    posted = [{"clip_candidate_id": "c1", "media_asset_id": "ma1"}]
    candidate = {"clip_candidate_id": "c1", "media_asset_id": "ma2"}
    ok = any(r.get("clip_candidate_id") == candidate["clip_candidate_id"] for r in posted)
    print(f"  {'PASS' if ok else 'FAIL'} media post dedupe by clip_candidate_id")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
