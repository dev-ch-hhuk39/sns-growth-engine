#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from transcribe_approved_source_videos import (  # noqa: E402
    build_transcript_row,
    eligible_videos,
    night_metadata_clip_eligible,
    save_rows,
    transcript_id_for,
)
from transcription.sheets_limits import MAX_SHEETS_CELL_CHARS  # noqa: E402


class RecordingSheets:
    def __init__(self):
        self.transcripts = []

    def save_video_transcript(self, row):
        self.transcripts.append(dict(row))
        return True

    def save_source_video(self, _row):
        return True

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
inactive, inactive_skipped = eligible_videos(
    [{**video, "source_id": "inactive_source"}],
    [],
    account_id="liver_manager",
    limit=3,
    allowed_source_ids={"active_source"},
)
bad_youtube_id, bad_youtube_id_skipped = eligible_videos(
    [{**video, "video_id": "UC0123456789012345678901", "canonical_video_url": "https://www.youtube.com/watch?v=UC0123456789012345678901"}],
    [],
    account_id="liver_manager",
    limit=3,
)
night_good = {**video, "source_video_id": "sv_ns_good", "account_id": "night_scout", "title": "キャバ嬢の店選び"}
night_bad = {**video, "source_video_id": "sv_ns_bad", "account_id": "night_scout", "title": "男性スカウトが語る求人"}
night_unknown = {**video, "source_video_id": "sv_ns_unknown", "account_id": "night_scout", "title": "HOSTCALL episode"}
night_selected, _ = eligible_videos([night_bad, night_unknown, night_good], [], account_id="night_scout", limit=3)
partial = build_transcript_row(
    {**video, "duration_seconds": 4004},
    {"text": "safe transcript", "segments": [{"start": 0, "end": 899, "text": "safe transcript"}], "processed_duration_seconds": 899},
)
large_row = {
    "transcript_id": "tr-persistence-boundary",
    "transcript_text": "あ" * 55_000,
    "segments_json": '[{"text":"' + ("い" * 55_000) + '"}]',
    "transcript_hash": "full-transcript-sha",
    "transcription_scope": "FULL",
}
recorder = RecordingSheets()
save_result = save_rows(recorder, [large_row], [])
persisted = recorder.transcripts[0]
checks = [
    ("eligible approved individual video", len(selected) == 1 and not skipped),
    ("transcript id stable", transcript_id_for(video) == "tr_sv_lm_1"),
    ("already transcribed skipped", not selected_after_done and "already_transcribed" in skipped_after_done[0]["reason"]),
    ("third party blocked", not bad and "rights_not_approved" in bad_skipped[0]["reason"]),
    ("inactive source blocked", not inactive and "source_not_active_for_media_autopilot" in inactive_skipped[0]["reason"]),
    ("youtube channel id blocked as video", not bad_youtube_id and "youtube_individual_video_id_required" in bad_youtube_id_skipped[0]["reason"]),
    ("night female subject metadata accepted", night_metadata_clip_eligible(night_good)[0]),
    ("night male scout metadata blocked", not night_metadata_clip_eligible(night_bad)[0]),
    ("night unknown subject metadata blocked", not night_metadata_clip_eligible(night_unknown)[0]),
    ("night transcription skips unsuitable videos", [row["source_video_id"] for row in night_selected] == ["sv_ns_good"]),
    ("bounded long transcription recorded as partial", partial["transcription_scope"] == "PARTIAL" and partial["processed_minutes"] < 15.1),
    ("runner persistence bounds long transcript cells", save_result["transcripts_saved"] == 1 and len(persisted["transcript_text"]) < MAX_SHEETS_CELL_CHARS and len(persisted["segments_json"]) < MAX_SHEETS_CELL_CHARS),
    ("runner persistence keeps transcript evidence", persisted["transcript_hash"] == "full-transcript-sha" and "SHEETS_BOUNDED" in persisted["transcription_scope"]),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
