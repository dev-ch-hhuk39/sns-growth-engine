#!/usr/bin/env python3
from media_growth_schemas import VIDEO_CLIP_CANDIDATE_FIELDS, build_clip_candidate

def main() -> int:
    row = build_clip_candidate({"source_id": "s", "source_url": "u", "source_platform": "youtube", "target_account_id": "liver_manager", "rights_status": "approved_creator_clip", "permission_status": "approved"})
    ok = all(f in row for f in VIDEO_CLIP_CANDIDATE_FIELDS)
    print(f"  {'PASS' if ok else 'FAIL'} clip candidate schema")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
