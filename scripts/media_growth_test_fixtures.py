"""Deterministic real-shape fixtures for media growth unit tests."""
from __future__ import annotations


def liver_video_and_transcript() -> tuple[dict, dict]:
    video = {
        "source_video_id": "sv_src_lm_yt_user_001_abcdefghijk",
        "source_id": "src_lm_yt_user_001",
        "account_id": "liver_manager",
        "platform": "youtube",
        "source_type": "channel",
        "source_url": "https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ",
        "video_id": "abcdefghijk",
        "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "original_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "title": "配信初心者が初見を迎えるときの話し方",
        "description_preview": "初見が入りやすい配信では、入室時の挨拶と今の話題を短く伝えます。",
        "duration_seconds": 60,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "discovery_status": "DISCOVERED",
    }
    transcript = {
        "transcript_id": f"tr_{video['source_video_id']}",
        "source_video_id": video["source_video_id"],
        "transcription_status": "DONE",
        "transcript_text": "配信で初見が入りやすくなるには、入室時の一言と話題の共有が大事です。",
        "segments_json": (
            '[{"start": 1, "end": 12, '
            '"text": "配信で初見が入りやすくなるには入室時の一言が大事です。"}]'
        ),
    }
    return video, transcript
