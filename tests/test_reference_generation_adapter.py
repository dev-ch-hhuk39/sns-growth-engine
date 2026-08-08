from __future__ import annotations

from generation.reference_generation_adapter import (
    build_current_reference_generation_inputs,
    enrich_source_post,
    native_video_id,
    resolve_source_video,
)


def _yt_video(video_id: str, *, source_video_id: str | None = None) -> dict:
    return {
        "source_video_id": source_video_id or f"sv_{video_id}",
        "source_id": "src_lm_yt_user_001",
        "account_id": "liver_manager",
        "platform": "youtube",
        "video_id": video_id,
        "canonical_video_url": f"https://www.youtube.com/watch?v={video_id}",
    }


def _yt_post(video_id: str) -> dict:
    return {
        "source_post_id": f"sp_{video_id}",
        "source_id": "src_lm_yt_user_001",
        "source_account_id": "src_lm_yt_user_001",
        "target_account_id": "liver_manager",
        "platform": "youtube",
        "external_post_id": video_id,
        "canonical_post_url": f"https://www.youtube.com/watch?v={video_id}",
    }


def test_native_video_id_ignores_youtube_channel_url():
    row = {"platform": "youtube", "canonical_post_url": "https://www.youtube.com/@creator/videos"}
    assert native_video_id(row) == ""


def test_native_video_id_parses_youtube_shorts_and_tiktok():
    assert native_video_id({"platform": "youtube", "canonical_post_url": "https://youtube.com/shorts/RjnZA9GzEEA"}) == "RjnZA9GzEEA"
    assert native_video_id({"platform": "tiktok", "canonical_post_url": "https://www.tiktok.com/@x/video/7662652624092597522"}) == "7662652624092597522"


def test_exact_youtube_id_selects_one_among_36_same_source_rows():
    wanted = "RjnZA9GzEEA"
    ids = [wanted] + [f"A{i:010d}"[-11:] for i in range(1, 36)]
    videos = [_yt_video(value) for value in ids]
    result = resolve_source_video(_yt_post(wanted), videos)
    assert result["status"] == "MATCHED"
    assert result["match"]["video_id"] == wanted
    assert len(result["matches"]) == 1


def test_channel_url_never_fans_out_to_same_source_videos():
    post = _yt_post("RjnZA9GzEEA")
    post["external_post_id"] = ""
    post["canonical_post_url"] = "https://www.youtube.com/@creator/videos"
    videos = [_yt_video("RjnZA9GzEEA"), _yt_video("jysDVWsvJKY")]
    result = resolve_source_video(post, videos)
    assert result["status"] == "UNMATCHED"
    assert result["reason"] == "native_video_id_missing"


def test_duplicate_exact_native_identity_fails_closed():
    post = _yt_post("RjnZA9GzEEA")
    videos = [
        _yt_video("RjnZA9GzEEA", source_video_id="sv_a"),
        _yt_video("RjnZA9GzEEA", source_video_id="sv_b"),
    ]
    result = resolve_source_video(post, videos)
    assert result["status"] == "AMBIGUOUS"
    assert len(result["matches"]) == 2


def test_existing_completed_transcript_is_attached_without_mutating_source():
    source = {
        "source_post_id": "sp_tt",
        "source_id": "src_lm_tt_user_001",
        "source_account_id": "src_lm_tt_user_001",
        "target_account_id": "liver_manager",
        "platform": "tiktok",
        "external_post_id": "7662652624092597522",
        "canonical_post_url": "https://www.tiktok.com/@x/video/7662652624092597522",
    }
    video = {
        "source_video_id": "sv_tt",
        "source_id": "src_lm_tt_user_001",
        "account_id": "liver_manager",
        "platform": "tiktok",
        "video_id": "7662652624092597522",
        "canonical_video_url": source["canonical_post_url"],
    }
    transcript = {
        "transcript_id": "tr_sv_tt",
        "account_id": "liver_manager",
        "source_video_id": "sv_tt",
        "transcription_status": "LOCAL_WHISPER_DONE",
        "transcription_provider": "local_faster_whisper",
        "transcript_text": "配信で初見さんへの声かけを改善する話です。",
    }
    enriched, state = enrich_source_post(source, [video], [transcript])
    assert state["status"] == "VIDEO_TRANSCRIPT_READY"
    assert enriched["transcript_text"] == transcript["transcript_text"]
    assert enriched["post_text"] == transcript["transcript_text"]
    assert "transcript_text" not in source


def test_video_without_transcript_remains_fail_closed():
    post = _yt_post("RjnZA9GzEEA")
    enriched, state = enrich_source_post(post, [_yt_video("RjnZA9GzEEA")], [])
    assert state["status"] == "TRANSCRIPT_MISSING"
    assert "transcript_text" not in enriched


def test_current_adapter_uses_ready_video_and_text_but_not_internal_rows():
    text_post = {
        "source_post_id": "sp_text",
        "source_id": "src_text",
        "source_account_id": "src_text",
        "target_account_id": "liver_manager",
        "platform": "threads",
        "canonical_post_url": "https://www.threads.net/@x/post/1",
        "original_post_text": "配信で初見コメントを増やすための実例です。",
    }
    video_post = _yt_post("RjnZA9GzEEA")
    internal = {
        "source_post_id": "sp_internal",
        "source_id": "system_generated",
        "source_account_id": "system_generated",
        "target_account_id": "liver_manager",
        "platform": "system_generated_owned",
        "original_post_text": "internal",
    }
    transcript = {
        "transcript_id": "tr_sv_RjnZA9GzEEA",
        "account_id": "liver_manager",
        "source_video_id": "sv_RjnZA9GzEEA",
        "transcription_status": "DONE",
        "transcript_text": "TikTok LIVEでリスナーとの会話を続ける具体策。",
    }
    result = build_current_reference_generation_inputs(
        account_id="liver_manager",
        source_posts=[text_post, video_post, internal],
        source_videos=[_yt_video("RjnZA9GzEEA")],
        transcripts=[transcript],
    )
    assert {row["post_id"] for row in result["posts"]} == {"sp_text", "sp_RjnZA9GzEEA"}
    assert len(result["scores"]) == 2
    assert result["diagnostics"]["video_transcript_ready"] == 1
    assert result["diagnostics"]["text_ready"] == 1
    assert result["diagnostics"]["internal_or_self_generated"] == 1
    assert result["diagnostics"]["ambiguous_match_count"] == 0



def test_reference_batch_stops_after_bounded_resource_exhausted(monkeypatch):
    import generate_threads_ideas_from_references as generator

    calls: list[str] = []

    def exhausted(*, source, **_kwargs):
        calls.append(str(source.get("post_id", "")))
        raise generator.ReferenceRewriteError(
            "Gemini API returned HTTP 429 (RESOURCE_EXHAUSTED: quota exhausted)"
        )

    monkeypatch.setattr(generator, "rewrite_reference_post", exhausted)
    posts = [
        {
            "post_id": "ref_1",
            "source_account_id": "external_creator",
            "platform": "threads",
            "original_post_text": "配信で初見コメントを増やす具体的な方法です。",
        },
        {
            "post_id": "ref_2",
            "source_account_id": "external_creator",
            "platform": "threads",
            "original_post_text": "配信でリスナーとの会話を続ける具体的な方法です。",
        },
    ]
    scores = [
        {"account_id": "liver_manager", "reference_post_id": "ref_1", "total_score": 2},
        {"account_id": "liver_manager", "reference_post_id": "ref_2", "total_score": 1},
    ]

    rows = generator.build_generation_rows(
        account_id="liver_manager",
        posts=posts,
        scores=scores,
        top_n=2,
    )

    assert calls == ["ref_1"]
    assert rows == {"drafts": [], "social_derivatives": [], "queue": []}
