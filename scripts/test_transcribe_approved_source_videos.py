#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from transcribe_approved_source_videos import eligible_videos, transcript_id_for  # noqa: E402

video = {
    "source_video_id": "sv_lm_1",
    "account_id": "liver_manager",
    "platform": "youtube",
    "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
    "video_id": "abcdefghijk",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
selected, skipped = eligible_videos([video], [], account_id="liver_manager", limit=3)
selected_after_done, skipped_after_done = eligible_videos(
    [video],
    [{"source_video_id": "sv_lm_1", "transcription_status": "DONE", "transcript_text": "done"}],
    account_id="liver_manager",
    limit=3,
)
bad, bad_skipped = eligible_videos([{**video, "rights_status": "third_party_reference_only"}], [], account_id="liver_manager", limit=3)
checks = [
    ("eligible approved individual video", len(selected) == 1 and not skipped),
    ("transcript id stable", transcript_id_for(video) == "tr_sv_lm_1"),
    ("already transcribed skipped", not selected_after_done and "already_transcribed" in skipped_after_done[0]["reason"]),
    ("third party blocked", not bad and "rights_not_approved" in bad_skipped[0]["reason"]),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
