#!/usr/bin/env python3
from media_growth_schemas import build_clip_candidate, build_media_pdca_records

def main() -> int:
    clip = build_clip_candidate({"source_id": "s", "target_account_id": "liver_manager", "rights_status": "approved_creator_clip", "permission_status": "approved"})
    records = build_media_pdca_records(clip, "m1")
    ok = all(v.get("clip_candidate_id") == clip["clip_candidate_id"] for k, v in records.items() if k != "learning_rules")
    print(f"  {'PASS' if ok else 'FAIL'} media PDCA records clip_candidate_id")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
