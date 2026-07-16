#!/usr/bin/env python3
from seed_owner_attested_media_permissions import eligible_sources, permission_row

rows = eligible_sources()
ids = {row["source_id"] for row in rows}
platforms = {str(row.get("source_platform") or row.get("platform")) for row in rows}
sample = permission_row(rows[0], "2026-07-17T00:00:00+00:00") if rows else {}
checks = [
    ("media platforms only", platforms <= {"threads", "youtube", "tiktok"}),
    ("active liver youtube included", "src_lm_yt_cand_001" in ids),
    ("note excluded", "src_lm_note_cand_001" not in ids),
    ("x excluded", all(not source_id.startswith("src_ns_x") for source_id in ids)),
    ("owner scope complete", all(sample.get(key) == "true" for key in ("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_transcription", "allow_cut", "allow_clip_repost", "allow_new_caption"))),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
