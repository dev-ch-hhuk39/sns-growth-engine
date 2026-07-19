#!/usr/bin/env python3
from discover_approved_source_videos import build_discovery_plan, load_sources
from media_growth_test_fixtures import fixture_caption_service
from run_media_growth_engine import build_media_growth_plan


def main() -> int:
    discovery = build_discovery_plan("night_scout")
    expected_active_sources = {
        row["source_id"]
        for row in load_sources()
        if row.get("active") is True
        and "night_scout" in (row.get("target_account_ids") or [row.get("target_account_id")])
        and row.get("media_autopilot_enabled") is True
    }
    # Placeholder discovery rows have no evidence about who appears in the
    # video, so they are analysis-only. A real discovered row with an explicit
    # female-subject metadata cue may create candidates.
    growth = build_media_growth_plan("night_scout")
    safe_growth = build_media_growth_plan(
        "night_scout",
        existing_source_videos=[{
            "source_video_id": "sv_ns_safe", "source_id": "src_ns_yt_cand_001",
            "account_id": "night_scout", "platform": "youtube",
            "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "title": "キャバ嬢の働き方", "description_preview": "女の子が店選びを考える動画",
            "duration_seconds": 50, "rights_status": "approved_creator_clip",
            "permission_status": "approved", "discovery_status": "DISCOVERED",
        }],
        existing_transcripts=[{
            "source_video_id": "sv_ns_safe", "transcript_id": "tr_ns_safe",
            "transcription_status": "DONE", "transcript_text": "客層と出勤の相談を先に整理すると続けやすいです。",
            "segments_json": '[{"start": 1, "end": 15, "text": "客層と出勤の相談を先に整理すると続けやすいです。"}, {"start": 20, "end": 40, "text": "女の子が無理なく働ける条件を見ます。"}]',
        }],
        caption_service=fixture_caption_service(),
    )
    checks = [
        ("night discovery selects active authorized sources", {row["source_id"] for row in discovery["selected_sources"]} == expected_active_sources),
        ("night discovery is bounded", discovery["limits"]["max_total_new_videos_per_run"] == 12),
        ("night growth plan is valid", growth["status"] == "PLAN_ONLY"),
        ("unknown night subject stays analysis only", growth["clip_candidate_count"] == 0),
        ("female-subject metadata creates candidates", safe_growth["clip_candidate_count"] > 0),
        ("night candidate metadata is night-specific", all("配信初心者" not in row.get("target_audience", "") for row in safe_growth["top_clip_candidates"])),
        ("night public text passes validator", safe_growth["final_public_post_validator"] == "PASS"),
        ("dry-run never performs external media actions", not any(safe_growth[key] for key in ("would_download", "would_cut", "would_upload", "would_post_video"))),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
