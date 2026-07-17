#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from transcribe_approved_source_videos import (  # noqa: E402
    build_transcript_row,
    eligible_videos,
    night_metadata_clip_eligible,
    transcript_id_for,
)

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
night_good = {**video, "source_video_id": "sv_ns_good", "account_id": "night_scout", "title": "キャバ嬢の店選び"}
night_bad = {**video, "source_video_id": "sv_ns_bad", "account_id": "night_scout", "title": "男性スカウトが語る求人"}
night_unknown = {**video, "source_video_id": "sv_ns_unknown", "account_id": "night_scout", "title": "HOSTCALL episode"}
night_selected, _ = eligible_videos([night_bad, night_unknown, night_good], [], account_id="night_scout", limit=3)
partial = build_transcript_row(
    {**video, "duration_seconds": 4004},
    {"text": "safe transcript", "segments": [{"start": 0, "end": 899, "text": "safe transcript"}], "processed_duration_seconds": 899},
)
checks = [
    ("eligible approved individual video", len(selected) == 1 and not skipped),
    ("transcript id stable", transcript_id_for(video) == "tr_sv_lm_1"),
    ("already transcribed skipped", not selected_after_done and "already_transcribed" in skipped_after_done[0]["reason"]),
    ("third party blocked", not bad and "rights_not_approved" in bad_skipped[0]["reason"]),
    ("night female subject metadata accepted", night_metadata_clip_eligible(night_good)[0]),
    ("night male scout metadata blocked", not night_metadata_clip_eligible(night_bad)[0]),
    ("night unknown subject metadata blocked", not night_metadata_clip_eligible(night_unknown)[0]),
    ("night transcription skips unsuitable videos", [row["source_video_id"] for row in night_selected] == ["sv_ns_good"]),
    ("bounded long transcription recorded as partial", partial["transcription_scope"] == "PARTIAL" and partial["processed_minutes"] < 15.1),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
