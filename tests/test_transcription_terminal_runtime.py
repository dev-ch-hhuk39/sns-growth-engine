from __future__ import annotations

from pathlib import Path

import transcribe_approved_source_videos as transcriber
from generation.reference_generation_adapter import (
    build_current_reference_generation_inputs,
    resolve_transcript,
)


def _video(source_video_id: str = "sv_test_1234567890123456789") -> dict[str, object]:
    return {
        "source_video_id": source_video_id,
        "account_id": "liver_manager",
        "source_id": "src_liver_test",
        "platform": "tiktok",
        "canonical_video_url": "https://www.tiktok.com/@creator/video/1234567890123456789",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
    }


def _transcript(status: str, *, text: str = "") -> dict[str, object]:
    return {
        "transcript_id": "tr_sv_test_1234567890123456789",
        "source_video_id": "sv_test_1234567890123456789",
        "account_id": "liver_manager",
        "transcription_status": status,
        "transcript_text": text,
        "updated_at": "2026-08-08T00:00:00+00:00",
    }


def test_media_runtime_installs_curl_cffi_extra() -> None:
    requirement = Path("requirements-acquisition.txt").read_text(encoding="utf-8")
    assert "yt-dlp[curl-cffi,default]==2026.7.4" in requirement
    assert "curl-cffi==0.15.0" in requirement


def test_tiktok_download_has_bounded_chrome_fallback() -> None:
    profiles = transcriber._ytdlp_audio_attempt_profiles("tiktok")
    assert profiles == (
        ("auto", {}),
        ("chrome", {"impersonate": "chrome"}),
    )
    assert transcriber._ytdlp_audio_attempt_profiles("youtube") == (("auto", {}),)


def test_terminal_transcript_is_not_reselected() -> None:
    selected, skipped = transcriber.eligible_videos(
        [_video()],
        [_transcript("NO_RELIABLE_SPEECH")],
        account_id="liver_manager",
        limit=5,
        allowed_source_ids={"src_liver_test"},
    )
    assert selected == []
    assert skipped[0]["reason"] == "terminal_transcription_state"


def test_single_empty_transcript_remains_retryable() -> None:
    selected, skipped = transcriber.eligible_videos(
        [_video()],
        [_transcript("LOCAL_WHISPER_EMPTY")],
        account_id="liver_manager",
        limit=5,
        allowed_source_ids={"src_liver_test"},
    )
    assert len(selected) == 1
    assert skipped == []


def test_repeated_empty_becomes_no_reliable_speech() -> None:
    current = {
        "transcription_status": "LOCAL_WHISPER_EMPTY",
        "error": "",
    }
    finalized = transcriber.finalize_transcription_status(
        _transcript("LOCAL_WHISPER_EMPTY"),
        current,
    )
    assert finalized["transcription_status"] == "NO_RELIABLE_SPEECH"
    assert finalized["error"] == "repeated_local_whisper_empty"


def test_adapter_exposes_terminal_separately_from_missing() -> None:
    video = _video()
    resolved = resolve_transcript(video, [_transcript("MEDIA_ACQUISITION_BLOCKED")])
    assert resolved["status"] == "TERMINAL"
    assert resolved["terminal_status"] == "MEDIA_ACQUISITION_BLOCKED"

    source_post = {
        "source_post_id": "sp_test_tiktok",
        "source_id": "src_liver_test",
        "source_account_id": "external_creator",
        "target_account_id": "liver_manager",
        "platform": "tiktok",
        "canonical_post_url": "https://www.tiktok.com/@creator/video/1234567890123456789",
        "external_post_id": "1234567890123456789",
    }
    adapted = build_current_reference_generation_inputs(
        account_id="liver_manager",
        source_posts=[source_post],
        source_videos=[video],
        transcripts=[_transcript("MEDIA_ACQUISITION_BLOCKED")],
    )
    diagnostics = adapted["diagnostics"]
    assert diagnostics["generation_ready"] == 0
    assert diagnostics["video_transcript_ready"] == 0
    assert diagnostics["video_transcript_missing"] == 0
    assert diagnostics["video_transcript_terminal"] == 1
    assert diagnostics["unresolved_video_sample"][0]["terminal_status"] == "MEDIA_ACQUISITION_BLOCKED"


def test_completed_transcript_wins_over_terminal_history() -> None:
    terminal = _transcript("NO_RELIABLE_SPEECH")
    done = {
        **_transcript("DONE", text="配信の会話を続ける具体的な内容"),
        "transcript_id": "tr_done",
        "transcript_hash": "same",
        "updated_at": "2026-08-09T00:00:00+00:00",
    }
    resolved = resolve_transcript(_video(), [terminal, done])
    assert resolved["status"] == "READY"
    assert resolved["match"]["transcript_id"] == "tr_done"
