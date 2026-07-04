#!/usr/bin/env python3
from media_growth_schemas import VIDEO_TRANSCRIPT_FIELDS, build_transcript_row

def main() -> int:
    row = build_transcript_row({"source_id": "s", "source_url": "u", "source_platform": "youtube", "rights_status": "approved_creator_clip", "permission_status": "approved"}, status="PLAN_ONLY")
    ok = all(f in row for f in VIDEO_TRANSCRIPT_FIELDS) and not row["transcript_text_redacted_preview"]
    print(f"  {'PASS' if ok else 'FAIL'} video transcript schema")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
