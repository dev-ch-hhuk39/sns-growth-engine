"""
test_phase218_220.py - Phase 2.18〜2.20 テストスイート

Phase 2.18: 動画 reference スキーマ（TAB_DEFINITIONS / SheetsClient / MockSheetsClient）
Phase 2.19: 動画収集アダプター（VideoSourceManager / YouTube / TikTok コレクター）
Phase 2.20: Cloudflare Whisper 文字起こし基盤（CloudflareWhisperClient / TranscriptionLimiter / TranscriptParser）
"""
from __future__ import annotations

import json
import os
import sys
import traceback

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

# ------------------------------------------------------------------ #
# テストランナー
# ------------------------------------------------------------------ #

_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
        except Exception as e:
            _results.append((name, False, f"{type(e).__name__}: {e}\n{traceback.format_exc()}"))
        return fn
    return decorator


# ------------------------------------------------------------------ #
# Phase 2.18: TAB_DEFINITIONS スキーマ
# ------------------------------------------------------------------ #

@test("TAB_DEFINITIONS に reference_sources タブが存在する")
def _():
    from sheets_client import TAB_DEFINITIONS
    assert "reference_sources" in TAB_DEFINITIONS


@test("reference_sources タブに必須列が存在する")
def _():
    from sheets_client import TAB_DEFINITIONS
    cols = TAB_DEFINITIONS["reference_sources"]
    for col in ["source_id", "account_id", "platform", "source_url", "handle", "priority", "active"]:
        assert col in cols, f"列 {col!r} が reference_sources に存在しない"


@test("TAB_DEFINITIONS に video_transcripts タブが存在する")
def _():
    from sheets_client import TAB_DEFINITIONS
    assert "video_transcripts" in TAB_DEFINITIONS


@test("video_transcripts タブに必須列が存在する")
def _():
    from sheets_client import TAB_DEFINITIONS
    cols = TAB_DEFINITIONS["video_transcripts"]
    for col in ["transcript_id", "account_id", "reference_post_id",
                "transcription_status", "transcript_text", "segments_json",
                "duration_seconds", "processed_minutes"]:
        assert col in cols, f"列 {col!r} が video_transcripts に存在しない"


@test("TAB_DEFINITIONS に video_clip_candidates タブが存在する")
def _():
    from sheets_client import TAB_DEFINITIONS
    assert "video_clip_candidates" in TAB_DEFINITIONS


@test("video_clip_candidates タブに必須列が存在する")
def _():
    from sheets_client import TAB_DEFINITIONS
    cols = TAB_DEFINITIONS["video_clip_candidates"]
    for col in ["clip_id", "account_id", "reference_post_id", "transcript_id",
                "start_time", "end_time", "duration_seconds", "hook",
                "clip_status", "rights_status", "permission_status"]:
        assert col in cols, f"列 {col!r} が video_clip_candidates に存在しない"


@test("TAB_DEFINITIONS に transcription_runs タブが存在する")
def _():
    from sheets_client import TAB_DEFINITIONS
    assert "transcription_runs" in TAB_DEFINITIONS


@test("transcription_runs タブに必須列が存在する")
def _():
    from sheets_client import TAB_DEFINITIONS
    cols = TAB_DEFINITIONS["transcription_runs"]
    for col in ["run_id", "date", "provider", "daily_limit_minutes",
                "used_minutes", "remaining_minutes", "processed_count",
                "skipped_daily_limit_count", "failed_count", "status"]:
        assert col in cols, f"列 {col!r} が transcription_runs に存在しない"


@test("reference_posts タブに video pipeline 用列が追加されている")
def _():
    from sheets_client import TAB_DEFINITIONS
    cols = TAB_DEFINITIONS["reference_posts"]
    for col in ["content_type", "video_id", "video_url", "creator_handle",
                "channel_id", "channel_name", "duration_seconds",
                "transcription_status", "clip_generation_status"]:
        assert col in cols, f"列 {col!r} が reference_posts に存在しない"


# ------------------------------------------------------------------ #
# Phase 2.18: MockSheetsClient
# ------------------------------------------------------------------ #

@test("MockSheetsClient.save_reference_source が動作する")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    source = {
        "source_id": "src-ns-yt-test",
        "account_id": "night_scout",
        "platform": "youtube",
        "source_url": "https://www.youtube.com/@test",
        "handle": "test_channel",
        "priority": 1,
        "active": "TRUE",
    }
    result = client.save_reference_source(source)
    assert result is True
    saved = client.find_reference_source_by_source_id("src-ns-yt-test")
    assert saved is not None
    assert saved["account_id"] == "night_scout"


@test("MockSheetsClient.get_reference_sources がフィルタリングできる")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    for i in range(3):
        client.save_reference_source({
            "source_id": f"src-ns-yt-{i}",
            "account_id": "night_scout",
            "platform": "youtube",
            "active": "TRUE",
        })
    client.save_reference_source({
        "source_id": "src-lm-tk-0",
        "account_id": "liver_manager",
        "platform": "tiktok",
        "active": "TRUE",
    })
    ns_sources = client.get_reference_sources(account_id="night_scout")
    assert len(ns_sources) == 3
    yt_sources = client.get_reference_sources(platform="youtube")
    assert len(yt_sources) == 3


@test("MockSheetsClient.update_reference_source が動作する")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    client.save_reference_source({"source_id": "src-test-001", "active": "TRUE"})
    result = client.update_reference_source("src-test-001", last_collected_at="2026-05-31T00:00:00Z")
    assert result is True
    src = client.find_reference_source_by_source_id("src-test-001")
    assert src["last_collected_at"] == "2026-05-31T00:00:00Z"


@test("MockSheetsClient.save_video_transcript が動作する")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    transcript = {
        "transcript_id": "tr-test-001",
        "account_id": "night_scout",
        "reference_post_id": "ref-yt-001",
        "transcription_status": "done",
        "transcript_text": "テストテキスト",
        "segments_json": "[]",
        "duration_seconds": 480,
        "processed_minutes": 8.0,
    }
    result = client.save_video_transcript(transcript)
    assert result is True
    saved = client.find_video_transcript_by_id("tr-test-001")
    assert saved is not None
    assert saved["transcription_status"] == "done"


@test("MockSheetsClient.get_video_transcripts が transcription_status でフィルタできる")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    for i, status in enumerate(["done", "done", "failed", "pending"]):
        client.save_video_transcript({
            "transcript_id": f"tr-{status}-{i}",
            "account_id": "night_scout",
            "transcription_status": status,
        })
    done = client.get_video_transcripts(transcription_status="done")
    assert len(done) == 2
    failed = client.get_video_transcripts(transcription_status="failed")
    assert len(failed) == 1


@test("MockSheetsClient.update_video_transcript が動作する")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    client.save_video_transcript({"transcript_id": "tr-upd-001", "transcription_status": "processing"})
    result = client.update_video_transcript("tr-upd-001", transcription_status="done", transcript_text="更新テキスト")
    assert result is True
    tr = client.find_video_transcript_by_id("tr-upd-001")
    assert tr["transcription_status"] == "done"
    assert tr["transcript_text"] == "更新テキスト"


@test("MockSheetsClient.save_video_clip_candidate が動作する")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    clip = {
        "clip_id": "clip-test-001",
        "account_id": "night_scout",
        "reference_post_id": "ref-yt-001",
        "transcript_id": "tr-test-001",
        "start_time": 0.0,
        "end_time": 60.0,
        "clip_status": "candidate",
    }
    result = client.save_video_clip_candidate(clip)
    assert result is True
    saved = client.find_video_clip_candidate_by_clip_id("clip-test-001")
    assert saved is not None
    assert saved["clip_status"] == "candidate"


@test("MockSheetsClient.get_video_clip_candidates がフィルタできる")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    client.save_video_clip_candidate({"clip_id": "clip-001", "account_id": "night_scout", "transcript_id": "tr-001", "clip_status": "candidate"})
    client.save_video_clip_candidate({"clip_id": "clip-002", "account_id": "night_scout", "transcript_id": "tr-002", "clip_status": "approved"})
    client.save_video_clip_candidate({"clip_id": "clip-003", "account_id": "liver_manager", "transcript_id": "tr-003", "clip_status": "candidate"})
    ns_clips = client.get_video_clip_candidates(account_id="night_scout")
    assert len(ns_clips) == 2
    candidates = client.get_video_clip_candidates(clip_status="candidate")
    assert len(candidates) == 2
    tr_clips = client.get_video_clip_candidates(transcript_id="tr-001")
    assert len(tr_clips) == 1


@test("MockSheetsClient.update_video_clip_candidate が動作する")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    client.save_video_clip_candidate({"clip_id": "clip-upd-001", "clip_status": "candidate"})
    result = client.update_video_clip_candidate("clip-upd-001", clip_status="approved")
    assert result is True
    clip = client.find_video_clip_candidate_by_clip_id("clip-upd-001")
    assert clip["clip_status"] == "approved"


@test("MockSheetsClient.save_transcription_run が動作する")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    run = {
        "run_id": "tr-run-001",
        "date": "2026-05-31",
        "provider": "cloudflare_whisper",
        "daily_limit_minutes": 120,
        "used_minutes": 18.0,
        "remaining_minutes": 102.0,
        "processed_count": 2,
        "skipped_daily_limit_count": 0,
        "failed_count": 0,
        "status": "completed",
    }
    result = client.save_transcription_run(run)
    assert result is True
    saved = client.get_transcription_run_by_date("2026-05-31")
    assert saved is not None
    assert float(saved["used_minutes"]) == 18.0


@test("MockSheetsClient.update_transcription_run が動作する")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    client.save_transcription_run({"run_id": "tr-run-upd-001", "date": "2026-05-31", "provider": "cloudflare_whisper", "used_minutes": 10.0})
    result = client.update_transcription_run("tr-run-upd-001", used_minutes=20.0)
    assert result is True
    run = client.get_transcription_run_by_date("2026-05-31")
    assert float(run["used_minutes"]) == 20.0


@test("MockSheetsClient.get_transcription_run_by_date は存在しない日付で None を返す")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    result = client.get_transcription_run_by_date("2099-01-01")
    assert result is None


@test("MockSheetsClient.save_video_transcript はアップサートができる")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    client.save_video_transcript({"transcript_id": "tr-upsert-001", "transcription_status": "processing"})
    client.save_video_transcript({"transcript_id": "tr-upsert-001", "transcription_status": "done"})
    results = client.get_video_transcripts()
    assert len(results) == 1
    assert results[0]["transcription_status"] == "done"


# ------------------------------------------------------------------ #
# Phase 2.19: video_source_manager
# ------------------------------------------------------------------ #

@test("build_source_id が決定論的な ID を生成する")
def _():
    from collectors.video_source_manager import build_source_id
    sid = build_source_id("night_scout", "youtube", "test_channel")
    assert sid == "src-night_scout-youtube-test_channel"
    sid2 = build_source_id("night_scout", "youtube", "@test_channel")
    assert sid2 == "src-night_scout-youtube-test_channel"


@test("normalize_source がデフォルト値を補完する")
def _():
    from collectors.video_source_manager import normalize_source
    normalized = normalize_source({
        "account_id": "night_scout",
        "platform": "YouTube",
        "handle": "test_ch",
        "source_url": "https://www.youtube.com/@test_ch",
    })
    assert normalized["platform"] == "youtube"
    assert normalized["active"] == "TRUE"
    assert normalized["collection_frequency"] == "daily"
    assert int(normalized["priority"]) == 5
    assert "source_id" in normalized


@test("get_active_sources が active=TRUE のソースのみ返す")
def _():
    from sheets_client import MockSheetsClient
    from collectors.video_source_manager import get_active_sources
    client = MockSheetsClient()
    client.save_reference_source({"source_id": "src-a", "account_id": "night_scout", "platform": "youtube", "active": "TRUE", "priority": 1})
    client.save_reference_source({"source_id": "src-b", "account_id": "night_scout", "platform": "youtube", "active": "FALSE", "priority": 2})
    active = get_active_sources(client, account_id="night_scout")
    assert len(active) == 1
    assert active[0]["source_id"] == "src-a"


@test("register_source が dry_run=True でも正規化済みdictを返す")
def _():
    from sheets_client import MockSheetsClient
    from collectors.video_source_manager import register_source
    client = MockSheetsClient()
    result = register_source(client, {
        "account_id": "night_scout",
        "platform": "youtube",
        "handle": "test_ch",
        "source_url": "https://www.youtube.com/@test_ch",
    }, dry_run=True)
    assert result["account_id"] == "night_scout"
    assert result["active"] == "TRUE"
    # dry_run なので保存されていない
    saved = client.find_reference_source_by_source_id(result["source_id"])
    assert saved is None


@test("register_source が dry_run=False で保存する")
def _():
    from sheets_client import MockSheetsClient
    from collectors.video_source_manager import register_source
    client = MockSheetsClient()
    result = register_source(client, {
        "account_id": "night_scout",
        "platform": "youtube",
        "handle": "test_ch_save",
        "source_url": "https://www.youtube.com/@test_ch_save",
    }, dry_run=False)
    saved = client.find_reference_source_by_source_id(result["source_id"])
    assert saved is not None


# ------------------------------------------------------------------ #
# Phase 2.19: youtube_video_collector
# ------------------------------------------------------------------ #

@test("normalize_youtube_video が基本フィールドを正規化する")
def _():
    from collectors.youtube_video_collector import normalize_youtube_video
    raw = {
        "video_id": "yt_test_001",
        "channel_id": "UCxxxxxx",
        "channel_name": "テストチャンネル",
        "title": "テスト動画タイトル",
        "description": "説明文",
        "duration_seconds": 480,
        "likes": 3200,
        "impressions": 85000,
        "comment_count": 142,
        "published_at": "2026-04-15T12:00:00Z",
    }
    result = normalize_youtube_video(raw, "night_scout")
    assert result["platform"] == "youtube"
    assert result["content_type"] == "video"
    assert result["video_id"] == "yt_test_001"
    assert result["likes"] == 3200
    assert result["duration_seconds"] == 480
    assert result["transcription_status"] == "pending"
    assert result["clip_generation_status"] == "pending"
    assert result["account_id"] == "night_scout"


@test("normalize_youtube_video が snippet 形式をパースできる")
def _():
    from collectors.youtube_video_collector import normalize_youtube_video
    raw = {
        "video_id": "yt_snippet_001",
        "snippet": {
            "title": "スニペット形式のタイトル",
            "channelId": "UCsnippet",
            "channelTitle": "スニペットチャンネル",
            "description": "スニペット説明文",
            "publishedAt": "2026-05-01T00:00:00Z",
            "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
        },
        "statistics": {"likeCount": "500", "viewCount": "10000", "commentCount": "50"},
        "contentDetails": {"duration": "PT8M30S"},
    }
    result = normalize_youtube_video(raw, "night_scout")
    assert result["title"] == "スニペット形式のタイトル"
    assert result["channel_id"] == "UCsnippet"
    assert result["duration_seconds"] == 510  # 8*60+30
    assert result["likes"] == 500
    assert result["thumbnail_url"] == "https://example.com/thumb.jpg"


@test("_parse_duration が ISO8601 duration を秒数に変換する")
def _():
    from collectors.youtube_video_collector import _parse_duration
    assert _parse_duration("PT4M30S", 0) == 270
    assert _parse_duration("PT1M0S", 0) == 60
    assert _parse_duration("PT0M45S", 0) == 45
    assert _parse_duration("PT10M", 0) == 600
    assert _parse_duration("", 120) == 120
    assert _parse_duration("invalid", 0) == 0


@test("youtube collect_from_mock が content_type=video のみを処理する")
def _():
    from collectors.youtube_video_collector import collect_from_mock
    videos = [
        {"platform": "youtube", "content_type": "video", "video_id": "v001", "title": "動画1"},
        {"platform": "youtube", "content_type": "text", "video_id": "v002"},
        {"platform": "x", "content_type": "text", "video_id": "v003"},
    ]
    results = collect_from_mock(videos, "night_scout")
    assert len(results) == 1
    assert results[0]["video_id"] == "v001"


@test("youtube collect_from_json_file がフィクスチャを読み込める")
def _():
    from collectors.youtube_video_collector import collect_from_json_file
    fixture_path = os.path.join(_V2_ROOT, "fixtures", "sample_video_references.json")
    results = collect_from_json_file(fixture_path, "night_scout")
    assert len(results) == 3
    for r in results:
        assert r["platform"] == "youtube"
        assert r["content_type"] == "video"
        assert r["transcription_status"] == "pending"


# ------------------------------------------------------------------ #
# Phase 2.19: tiktok_video_collector
# ------------------------------------------------------------------ #

@test("normalize_tiktok_video が基本フィールドを正規化する")
def _():
    from collectors.tiktok_video_collector import normalize_tiktok_video
    raw = {
        "video_id": "tk_test_001",
        "creator_handle": "test_creator",
        "title": "テストTikTok動画",
        "duration_seconds": 180,
        "likes": 12000,
        "impressions": 230000,
        "comment_count": 456,
        "reposts": 890,
    }
    result = normalize_tiktok_video(raw, "night_scout")
    assert result["platform"] == "tiktok"
    assert result["content_type"] == "video"
    assert result["video_id"] == "tk_test_001"
    assert result["likes"] == 12000
    assert result["reposts"] == 890
    assert result["transcription_status"] == "pending"
    assert result["account_id"] == "night_scout"


@test("normalize_tiktok_video が TikTok API 形式（diggCount等）をパースできる")
def _():
    from collectors.tiktok_video_collector import normalize_tiktok_video
    raw = {
        "video_id": "tk_api_001",
        "author": "@api_creator",
        "desc": "API形式の説明文",
        "diggCount": 5000,
        "commentCount": 200,
        "shareCount": 150,
        "playCount": 80000,
        "duration": 90,
        "cover": "https://example.com/cover.jpg",
    }
    result = normalize_tiktok_video(raw, "liver_manager")
    assert result["likes"] == 5000
    assert result["comment_count"] == 200
    assert result["reposts"] == 150
    assert result["impressions"] == 80000
    assert result["duration_seconds"] == 90
    assert result["thumbnail_url"] == "https://example.com/cover.jpg"


@test("tiktok collect_from_mock が platform=tiktok のみを処理する")
def _():
    from collectors.tiktok_video_collector import collect_from_mock
    videos = [
        {"platform": "tiktok", "video_id": "tk001", "title": "TikTok動画"},
        {"platform": "youtube", "video_id": "yt001"},
        {"platform": "x", "video_id": "x001"},
    ]
    results = collect_from_mock(videos, "night_scout")
    assert len(results) == 1
    assert results[0]["video_id"] == "tk001"


@test("tiktok collect_from_json_file がフィクスチャを読み込める")
def _():
    from collectors.tiktok_video_collector import collect_from_json_file
    fixture_path = os.path.join(_V2_ROOT, "fixtures", "sample_video_references.json")
    results = collect_from_json_file(fixture_path, "night_scout")
    assert len(results) == 2
    for r in results:
        assert r["platform"] == "tiktok"
        assert r["content_type"] == "video"


@test("tiktok save_video_references が dry_run=True で保存しない")
def _():
    from sheets_client import MockSheetsClient
    from collectors.tiktok_video_collector import normalize_tiktok_video, save_video_references
    client = MockSheetsClient()
    refs = [normalize_tiktok_video({"video_id": "tk999", "platform": "tiktok"}, "night_scout")]
    result = save_video_references(client, refs, dry_run=True)
    assert result["added"] == 0
    assert result["skipped"] == 1


# ------------------------------------------------------------------ #
# Phase 2.20: config_loader
# ------------------------------------------------------------------ #

@test("get_transcription_config がデフォルト値を返す")
def _():
    from config_loader import get_transcription_config
    cfg = get_transcription_config()
    assert "allow_transcription_api" in cfg
    assert cfg["allow_transcription_api"] is False
    assert "daily_limit_minutes" in cfg
    assert int(cfg["daily_limit_minutes"]) >= 1
    assert "provider" in cfg


@test("get_transcription_config の allow_transcription_api はデフォルト False")
def _():
    from config_loader import get_transcription_config
    cfg = get_transcription_config()
    # ALLOW_TRANSCRIPTION_API=false がデフォルト値
    assert cfg["allow_transcription_api"] is False


# ------------------------------------------------------------------ #
# Phase 2.20: CloudflareWhisperClient
# ------------------------------------------------------------------ #

@test("CloudflareWhisperClient.from_config が dry_run モードで生成される")
def _():
    from transcription.cloudflare_whisper_client import CloudflareWhisperClient
    cfg = {
        "account_id": "",
        "api_token": None,
        "allow_transcription_api": False,
        "provider": "cloudflare_whisper",
        "daily_limit_minutes": 120,
    }
    client = CloudflareWhisperClient.from_config(cfg, dry_run=True)
    assert client._dry_run is True


@test("CloudflareWhisperClient.transcribe が dry_run でモックレスポンスを返す")
def _():
    from transcription.cloudflare_whisper_client import CloudflareWhisperClient
    client = CloudflareWhisperClient(
        account_id="",
        api_token=None,
        allow_transcription_api=False,
        dry_run=True,
    )
    result = client.transcribe(
        "test.mp3",
        reference_post_id="ref-yt-001",
        transcript_id="tr-test-001",
        duration_seconds=480.0,
    )
    assert result.status == "done"
    assert len(result.transcript_text) > 0
    assert result.transcript_id == "tr-test-001"
    assert result.reference_post_id == "ref-yt-001"
    assert result.duration_seconds == 480.0
    assert result.processed_minutes == 8.0


@test("TranscriptionResult.to_sheets_row が video_transcripts 行フォーマットを返す")
def _():
    from transcription.cloudflare_whisper_client import TranscriptionResult
    result = TranscriptionResult(
        transcript_id="tr-001",
        reference_post_id="ref-yt-001",
        status="done",
        transcript_text="テスト",
        segments=[{"word": "テスト", "start": 0.0, "end": 0.5}],
        language="ja",
        duration_seconds=120.0,
        processed_minutes=2.0,
        error="",
    )
    row = result.to_sheets_row()
    assert row["transcript_id"] == "tr-001"
    assert row["reference_post_id"] == "ref-yt-001"
    assert row["transcription_status"] == "done"
    assert row["processed_minutes"] == 2.0
    segments = json.loads(row["segments_json"])
    assert isinstance(segments, list)
    assert segments[0]["word"] == "テスト"


@test("CloudflareWhisperClient は allow_transcription_api=False の場合 always dry_run になる")
def _():
    from transcription.cloudflare_whisper_client import CloudflareWhisperClient
    # ALLOW_TRANSCRIPTION_API=false で dry_run=False にしようとしても mock になる
    client = CloudflareWhisperClient.from_config(
        {"account_id": "", "api_token": None, "allow_transcription_api": False, "daily_limit_minutes": 120},
        dry_run=False,
    )
    result = client.transcribe(
        "fake.mp3",
        reference_post_id="ref-test",
        transcript_id="tr-forced-mock",
        duration_seconds=60.0,
    )
    assert result.status == "done"
    assert result.provider == "cloudflare_whisper_mock"


# ------------------------------------------------------------------ #
# Phase 2.20: TranscriptionLimiter
# ------------------------------------------------------------------ #

@test("TranscriptionLimiter が初期状態で残り120分になる")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    limiter = TranscriptionLimiter(client, "2026-05-31", limit_minutes=120.0)
    assert limiter.remaining_minutes == 120.0
    assert limiter.used_minutes == 0.0


@test("TranscriptionLimiter が既存 run から使用量を引き継ぐ")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    client.save_transcription_run({
        "run_id": "tr-existing-001",
        "date": "2026-05-31",
        "provider": "cloudflare_whisper",
        "used_minutes": 50.0,
        "processed_count": 5,
        "skipped_daily_limit_count": 1,
        "failed_count": 0,
    })
    limiter = TranscriptionLimiter(client, "2026-05-31", limit_minutes=120.0)
    assert limiter.used_minutes == 50.0
    assert limiter.remaining_minutes == 70.0


@test("TranscriptionLimiter.can_process が上限内の動画を許可する")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    limiter = TranscriptionLimiter(client, "2026-05-31", limit_minutes=10.0)
    assert limiter.can_process(300.0) is True   # 5分
    assert limiter.can_process(600.0) is True   # 10分
    assert limiter.can_process(601.0) is False  # 超過


@test("TranscriptionLimiter.record が使用量を累積する")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    limiter = TranscriptionLimiter(client, "2026-05-31", limit_minutes=120.0)
    limiter.record(duration_seconds=300.0, status="done")
    assert abs(limiter.used_minutes - 5.0) < 0.01
    assert limiter.remaining_minutes < 116.0
    limiter.record(duration_seconds=600.0, status="done")
    assert abs(limiter.used_minutes - 15.0) < 0.01


@test("TranscriptionLimiter.record_skip がスキップカウントを増やす")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    limiter = TranscriptionLimiter(client, "2026-05-31", limit_minutes=120.0)
    limiter.record_skip()
    limiter.record_skip()
    summary = limiter.summary()
    assert summary["skipped_daily_limit_count"] == 2
    assert summary["used_minutes"] == 0.0


@test("TranscriptionLimiter.flush が dry_run=False で Sheets に書き戻す")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    limiter = TranscriptionLimiter(client, "2026-06-01", limit_minutes=120.0, dry_run=False)
    limiter.record(duration_seconds=480.0, status="done")
    result = limiter.flush()
    assert result is True
    run = client.get_transcription_run_by_date("2026-06-01")
    assert run is not None
    assert float(run["used_minutes"]) == 8.0
    assert int(run["processed_count"]) == 1


@test("TranscriptionLimiter.flush は2回目で False を返す（冪等）")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    limiter = TranscriptionLimiter(client, "2026-06-02", limit_minutes=120.0, dry_run=False)
    limiter.flush()
    result = limiter.flush()
    assert result is False


@test("TranscriptionLimiter.flush が dry_run=True で False を返す")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    limiter = TranscriptionLimiter(client, "2026-06-03", limit_minutes=120.0, dry_run=True)
    limiter.record(300.0, "done")
    result = limiter.flush()
    assert result is False


@test("TranscriptionLimiter.summary が正しい集計を返す")
def _():
    from sheets_client import MockSheetsClient
    from transcription.transcription_limiter import TranscriptionLimiter
    client = MockSheetsClient()
    limiter = TranscriptionLimiter(client, "2026-06-04", limit_minutes=60.0)
    limiter.record(300.0, "done")
    limiter.record(300.0, "failed")
    limiter.record_skip()
    s = limiter.summary()
    assert s["processed_count"] == 1
    assert s["failed_count"] == 1
    assert s["skipped_daily_limit_count"] == 1
    assert abs(s["used_minutes"] - 5.0) < 0.01


# ------------------------------------------------------------------ #
# Phase 2.20: transcript_parser
# ------------------------------------------------------------------ #

@test("parse_segments が JSON 文字列をパースする")
def _():
    from transcription.transcript_parser import parse_segments
    json_str = '[{"word": "テスト", "start": 0.0, "end": 0.5}]'
    result = parse_segments(json_str)
    assert isinstance(result, list)
    assert result[0]["word"] == "テスト"


@test("parse_segments がリストをそのまま返す")
def _():
    from transcription.transcript_parser import parse_segments
    segs = [{"word": "テスト", "start": 0.0, "end": 0.5}]
    result = parse_segments(segs)
    assert result == segs


@test("parse_segments が空文字列で空リストを返す")
def _():
    from transcription.transcript_parser import parse_segments
    assert parse_segments("") == []
    assert parse_segments(None) == []
    assert parse_segments([]) == []


@test("extract_clip_window がセグメントから区間を返す")
def _():
    from transcription.transcript_parser import extract_clip_window
    segments = [
        {"word": "a", "start": 0.0, "end": 0.5},
        {"word": "b", "start": 0.5, "end": 1.0},
        {"word": "c", "start": 1.0, "end": 16.0},
    ]
    start, end = extract_clip_window(segments)
    assert start == 0.0
    assert end == 16.0


@test("extract_clip_window が max_duration を超える場合はカットする")
def _():
    from transcription.transcript_parser import extract_clip_window
    segments = [
        {"word": "a", "start": 0.0, "end": 400.0},
    ]
    start, end = extract_clip_window(segments, max_duration=300.0)
    assert end - start <= 300.0


@test("extract_clip_window が短すぎるセグメントで (0.0, 0.0) を返す")
def _():
    from transcription.transcript_parser import extract_clip_window
    segments = [{"word": "a", "start": 0.0, "end": 5.0}]
    start, end = extract_clip_window(segments, min_duration=15.0)
    assert start == 0.0 and end == 0.0


@test("extract_clip_window が空セグメントで (0.0, 0.0) を返す")
def _():
    from transcription.transcript_parser import extract_clip_window
    assert extract_clip_window([]) == (0.0, 0.0)


@test("extract_hook_sentence が最初の句読点で区切る")
def _():
    from transcription.transcript_parser import extract_hook_sentence
    text = "キャバ嬢として月100万稼ぐには、まず店選びが全てです。良い店は面接の対応から違います。"
    hook = extract_hook_sentence(text)
    assert hook.endswith("。")
    assert "月100万" in hook or "店選び" in hook


@test("extract_hook_sentence が句読点なしの場合は先頭40文字を返す")
def _():
    from transcription.transcript_parser import extract_hook_sentence
    text = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりる"
    hook = extract_hook_sentence(text)
    assert len(hook) <= 40


@test("extract_hook_sentence が空文字列で空文字列を返す")
def _():
    from transcription.transcript_parser import extract_hook_sentence
    assert extract_hook_sentence("") == ""


@test("build_clip_candidate が transcript から候補を生成する")
def _():
    from transcription.transcript_parser import build_clip_candidate
    transcript = {
        "transcript_id": "tr-001",
        "reference_post_id": "ref-yt-001",
        "source_platform": "youtube",
        "video_url": "https://www.youtube.com/watch?v=test",
        "transcript_text": "キャバ嬢として月100万稼ぐには、まず店選びが全てです。",
        "segments_json": '[{"word": "キャバ嬢", "start": 0.0, "end": 0.8}, {"word": "全てです", "start": 3.7, "end": 30.0}]',
        "duration_seconds": 480,
        "transcription_status": "done",
    }
    candidate = build_clip_candidate(transcript, account_id="night_scout")
    assert candidate is not None
    assert candidate["account_id"] == "night_scout"
    assert candidate["transcript_id"] == "tr-001"
    assert candidate["reference_post_id"] == "ref-yt-001"
    assert candidate["clip_status"] == "candidate"
    assert float(candidate["duration_seconds"]) > 0
    assert candidate["hook"] != ""
    assert candidate["rights_status"] == "unknown"


@test("build_clip_candidate が duration=0 かつセグメントなしで None を返す")
def _():
    from transcription.transcript_parser import build_clip_candidate
    transcript = {
        "transcript_id": "tr-empty",
        "reference_post_id": "ref-empty",
        "transcript_text": "短い",
        "segments_json": "[]",
        "duration_seconds": 0,
    }
    result = build_clip_candidate(transcript, account_id="night_scout")
    assert result is None


@test("build_clip_candidates_from_transcripts が done のみを処理する")
def _():
    from transcription.transcript_parser import build_clip_candidates_from_transcripts
    transcripts = [
        {
            "transcript_id": "tr-done-001",
            "reference_post_id": "ref-001",
            "transcription_status": "done",
            "transcript_text": "テスト文字起こし結果。この動画は夜職に関する内容です。",
            "segments_json": '[{"word": "テスト", "start": 0.0, "end": 20.0}]',
            "duration_seconds": 120,
            "source_platform": "youtube",
            "video_url": "https://www.youtube.com/watch?v=test",
        },
        {
            "transcript_id": "tr-failed-001",
            "reference_post_id": "ref-002",
            "transcription_status": "failed",
            "transcript_text": "",
            "segments_json": "[]",
            "duration_seconds": 0,
        },
        {
            "transcript_id": "tr-pending-001",
            "reference_post_id": "ref-003",
            "transcription_status": "pending",
            "transcript_text": "",
            "segments_json": "[]",
            "duration_seconds": 0,
        },
    ]
    candidates = build_clip_candidates_from_transcripts(transcripts, account_id="night_scout")
    assert len(candidates) == 1
    assert candidates[0]["transcript_id"] == "tr-done-001"


# ------------------------------------------------------------------ #
# Phase 2.20: フィクスチャ検証
# ------------------------------------------------------------------ #

@test("sample_video_references.json が正しい構造を持つ")
def _():
    fixture_path = os.path.join(_V2_ROOT, "fixtures", "sample_video_references.json")
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    assert "youtube" in data
    assert "tiktok" in data
    assert len(data["youtube"]) >= 3
    assert len(data["tiktok"]) >= 2
    for v in data["youtube"]:
        assert v["content_type"] == "video"
        assert v["platform"] == "youtube"
        assert v["transcription_status"] == "pending"
    for v in data["tiktok"]:
        assert v["content_type"] == "video"
        assert v["platform"] == "tiktok"


@test("sample_cloudflare_whisper_response.json が正しい構造を持つ")
def _():
    fixture_path = os.path.join(_V2_ROOT, "fixtures", "sample_cloudflare_whisper_response.json")
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["success"] is True
    assert "result" in data
    assert "text" in data["result"]
    assert len(data["result"]["text"]) > 0
    assert "words" in data["result"]
    assert len(data["result"]["words"]) > 0


@test("sample_transcript_segments.json が正しい構造を持つ")
def _():
    fixture_path = os.path.join(_V2_ROOT, "fixtures", "sample_transcript_segments.json")
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) >= 2
    done_items = [d for d in data if d.get("transcription_status") == "done"]
    assert len(done_items) >= 1
    for item in done_items:
        assert "transcript_id" in item
        assert "reference_post_id" in item
        assert "transcript_text" in item


# ------------------------------------------------------------------ #
# Phase 2.20: .env.template 更新確認
# ------------------------------------------------------------------ #

@test(".env.template に ALLOW_TRANSCRIPTION_API=false が含まれる")
def _():
    template_path = os.path.join(_V2_ROOT, ".env.template")
    with open(template_path, encoding="utf-8") as f:
        content = f.read()
    assert "ALLOW_TRANSCRIPTION_API=false" in content


@test(".env.template に CLOUDFLARE_ACCOUNT_ID が含まれる")
def _():
    template_path = os.path.join(_V2_ROOT, ".env.template")
    with open(template_path, encoding="utf-8") as f:
        content = f.read()
    assert "CLOUDFLARE_ACCOUNT_ID=" in content
    assert "CLOUDFLARE_API_TOKEN=" in content


@test(".env.template に DAILY_TRANSCRIPTION_MINUTES_LIMIT が含まれる")
def _():
    template_path = os.path.join(_V2_ROOT, ".env.template")
    with open(template_path, encoding="utf-8") as f:
        content = f.read()
    assert "DAILY_TRANSCRIPTION_MINUTES_LIMIT=120" in content


# ------------------------------------------------------------------ #
# 統合テスト
# ------------------------------------------------------------------ #

@test("エンドツーエンド: YouTube動画収集 → 保存 → 文字起こし → クリップ候補生成")
def _():
    from sheets_client import MockSheetsClient
    from collectors.youtube_video_collector import normalize_youtube_video, save_video_references
    from transcription.cloudflare_whisper_client import CloudflareWhisperClient
    from transcription.transcription_limiter import TranscriptionLimiter
    from transcription.transcript_parser import build_clip_candidate
    import uuid

    client = MockSheetsClient()

    # Step1: 動画を収集・保存
    raw_video = {
        "video_id": f"yt_e2e_{str(uuid.uuid4())[:6]}",
        "channel_name": "テストチャンネル",
        "title": "テスト動画：夜職の選び方を徹底解説します。",
        "duration_seconds": 360,
        "likes": 1000,
        "impressions": 20000,
        "published_at": "2026-05-31T00:00:00Z",
    }
    ref = normalize_youtube_video(raw_video, "night_scout")
    result = save_video_references(client, [ref], dry_run=False)
    assert result["added"] == 1

    # Step2: 文字起こし
    whisper = CloudflareWhisperClient(account_id="", api_token=None, dry_run=True)
    limiter = TranscriptionLimiter(client, "2026-05-31", limit_minutes=120.0, dry_run=False)
    assert limiter.can_process(360.0) is True

    tr_result = whisper.transcribe(
        "dummy.mp3",
        reference_post_id=ref["id"],
        transcript_id=f"tr-e2e-{str(uuid.uuid4())[:6]}",
        duration_seconds=360.0,
    )
    assert tr_result.status == "done"
    limiter.record(360.0, "done")

    # Step3: Sheetsに保存
    row = tr_result.to_sheets_row()
    row["account_id"] = "night_scout"
    row["source_platform"] = "youtube"
    row["video_url"] = ref["video_url"]
    row["reference_post_id"] = ref["id"]
    client.save_video_transcript(row)

    # Step4: クリップ候補生成
    transcript_data = client.find_video_transcript_by_id(tr_result.transcript_id)
    assert transcript_data is not None
    candidate = build_clip_candidate(transcript_data, account_id="night_scout")
    assert candidate is not None
    client.save_video_clip_candidate(candidate)

    # Step5: limiter flush
    limiter.flush()
    run = client.get_transcription_run_by_date("2026-05-31")
    assert run is not None
    assert int(run["processed_count"]) == 1

    # 最終確認
    clips = client.get_video_clip_candidates(account_id="night_scout")
    assert len(clips) == 1


@test("エンドツーエンド: TikTok動画収集 → mock 文字起こし")
def _():
    from sheets_client import MockSheetsClient
    from collectors.tiktok_video_collector import normalize_tiktok_video, save_video_references
    from transcription.cloudflare_whisper_client import CloudflareWhisperClient

    client = MockSheetsClient()
    raw = {
        "video_id": "tk_e2e_001",
        "creator_handle": "test_creator",
        "title": "夜職を始めて3ヶ月で変わったこと。正直な体験談。",
        "duration_seconds": 180,
        "likes": 8000,
        "impressions": 150000,
    }
    ref = normalize_tiktok_video(raw, "night_scout")
    result = save_video_references(client, [ref], dry_run=False)
    assert result["added"] == 1

    whisper = CloudflareWhisperClient(account_id="", api_token=None, dry_run=True)
    tr_result = whisper.transcribe(
        "dummy.mp3",
        reference_post_id=ref["id"],
        transcript_id="tr-tk-e2e-001",
        duration_seconds=180.0,
    )
    assert tr_result.status == "done"
    assert tr_result.processed_minutes == 3.0


@test("MockSheetsClient に video pipeline の全メソッドが揃っている")
def _():
    from sheets_client import MockSheetsClient
    client = MockSheetsClient()
    methods = [
        "get_reference_sources", "find_reference_source_by_source_id",
        "save_reference_source", "update_reference_source",
        "get_video_transcripts", "find_video_transcript_by_reference_post_id",
        "find_video_transcript_by_id", "save_video_transcript", "update_video_transcript",
        "get_video_clip_candidates", "find_video_clip_candidate_by_clip_id",
        "save_video_clip_candidate", "update_video_clip_candidate",
        "get_transcription_run_by_date", "save_transcription_run", "update_transcription_run",
    ]
    for method in methods:
        assert hasattr(client, method), f"MockSheetsClient に {method!r} メソッドが存在しない"


# ------------------------------------------------------------------ #
# 結果出力
# ------------------------------------------------------------------ #

def _print_results() -> int:
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    print("\n" + "=" * 70)
    print(f"Phase 2.18〜2.20 テスト結果: {passed} PASS / {failed} FAIL")
    print("=" * 70)
    if failed:
        for name, ok, err in _results:
            if not ok:
                print(f"\n[FAIL] {name}")
                print(err)
    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(_print_results())
