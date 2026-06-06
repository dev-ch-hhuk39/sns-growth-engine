"""
test_phase225_228.py - Phase 2.25-2.28 テストスイート

テスト範囲:
  2.25: run_video_pipeline.py（統合実行 CLI の各ステップ関数）
  2.26: video_downloader / audio_extractor（dry-run・エラーハンドリング）
  2.27: test_cloudflare_transcription_credentials（env check 動作）
  2.28: 権利レビューワークフロー（_needs_rights_review / rights_review_required フィールド）
  共通: check_pipeline_integrity Phase 2.28 拡張チェック
  フィクスチャ: sample_video_downloader_result / sample_audio_extractor_result / sample_pipeline_run_result
"""
from __future__ import annotations

import json
import os
import sys
import uuid

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))
sys.path.insert(0, os.path.join(_V2_ROOT, "scripts"))

from sheets_client import MockSheetsClient
from video.video_downloader import download_video, download_videos_batch, _extract_video_id
from video.audio_extractor import extract_audio, extract_audio_batch
from generation.video_clip_generator import (
    _is_rights_blocked,
    _needs_rights_review,
    save_clip_generation_result,
    generate_from_clips_batch,
)

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def _test(name: str, fn) -> None:
    try:
        fn()
        _results.append((PASS, name))
        print(f"  [PASS] {name}")
    except Exception as e:
        _results.append((FAIL, name))
        print(f"  [FAIL] {name}: {e}")


def _make_candidate(**kwargs) -> dict:
    base = {
        "clip_id": f"clip-{str(uuid.uuid4())[:8]}",
        "account_id": "night_scout",
        "reference_post_id": "ref-yt-test",
        "transcript_id": "tr-test-001",
        "source_platform": "youtube",
        "source_video_url": "https://www.youtube.com/watch?v=test",
        "start_time": "00:01:00",
        "end_time": "00:02:00",
        "duration_seconds": 60,
        "clip_title": "テストクリップ",
        "hook": "テストフック",
        "clip_status": "candidate",
        "media_reuse_risk": "low",
        "imitation_risk": "low",
        "rights_status": "unknown",
        "permission_status": "unknown",
        "text_generation_status": "pending",
    }
    base.update(kwargs)
    return base


def _make_reference_post(**kwargs) -> dict:
    base = {
        "id": f"ref-{str(uuid.uuid4())[:8]}",
        "account_id": "night_scout",
        "platform": "youtube",
        "content_type": "video",
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "duration_seconds": 300,
        "transcription_status": "pending",
    }
    base.update(kwargs)
    return base


def _make_gen() -> dict:
    return {
        "x_text": "テストX投稿文",
        "threads_text": "テストThreads投稿文",
        "title": "テスト下書き",
        "hypothesis": "テスト仮説",
        "media_strategy": "none",
    }


# ============================================================
# Phase 2.28: 権利レビューワークフロー
# ============================================================

print("\n=== Phase 2.28: 権利レビューワークフロー ===")


def t_needs_rights_review_unknown():
    c = _make_candidate(rights_status="unknown")
    assert _needs_rights_review(c) is True


def t_needs_rights_review_allowed():
    c = _make_candidate(rights_status="allowed")
    assert _needs_rights_review(c) is False


def t_needs_rights_review_not_allowed():
    # not_allowed は _is_rights_blocked でブロックされるが _needs_rights_review はFalse
    c = _make_candidate(rights_status="not_allowed")
    assert _needs_rights_review(c) is False


def t_rights_blocked_unknown_is_false():
    # Phase 2.28: unknown はブロックしない
    c = _make_candidate(rights_status="unknown")
    assert _is_rights_blocked(c) is False


def t_rights_blocked_not_allowed_is_true():
    c = _make_candidate(rights_status="not_allowed")
    assert _is_rights_blocked(c) is True


def t_rights_blocked_high_risk_is_true():
    c = _make_candidate(rights_status="allowed", media_reuse_risk="high")
    assert _is_rights_blocked(c) is True


def t_save_clip_gen_unknown_sets_rights_review_required():
    client = MockSheetsClient()
    c = _make_candidate(rights_status="unknown")
    gen = _make_gen()
    result = save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    assert result["rights_review_required"] is True
    assert result["rights_blocked"] is False
    # queue に rights_review_required=true が設定されていること
    for q in client._queue:
        assert q.get("rights_review_required") == "true"


def t_save_clip_gen_allowed_no_rights_review_required():
    client = MockSheetsClient()
    c = _make_candidate(rights_status="allowed", permission_status="granted")
    gen = _make_gen()
    result = save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    assert result["rights_review_required"] is False
    assert result["rights_blocked"] is False
    for q in client._queue:
        assert q.get("rights_review_required") == "false"


def t_save_clip_gen_generation_mode_video_clip_reference():
    # generation_mode が "video_clip_reference" になっていること
    client = MockSheetsClient()
    c = _make_candidate(rights_status="allowed")
    gen = _make_gen()
    save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    for d in client._drafts:
        assert d.get("generation_mode") == "video_clip_reference", (
            f"generation_mode が video_clip_reference でない: {d.get('generation_mode')!r}"
        )
    for q in client._queue:
        assert q.get("generation_mode") == "video_clip_reference"


def t_save_clip_gen_queue_has_source_fields():
    # queue に source_video_url / source_time_range / media_reuse_risk が設定されること
    client = MockSheetsClient()
    c = _make_candidate(
        rights_status="allowed",
        source_video_url="https://www.youtube.com/watch?v=test",
        start_time="00:01:00",
        end_time="00:02:00",
        media_reuse_risk="medium",
    )
    gen = _make_gen()
    save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    for q in client._queue:
        assert q.get("source_video_url") == "https://www.youtube.com/watch?v=test"
        assert "00:01:00" in q.get("source_time_range", "")
        assert q.get("media_reuse_risk") == "medium"


def t_batch_unknown_all_in_queue_rights_review():
    client = MockSheetsClient()
    candidates = [_make_candidate(rights_status="unknown") for _ in range(3)]
    acc = {"account_id": "night_scout"}
    stats = generate_from_clips_batch(candidates, client, acc, mock_llm=True, dry_run=False)
    assert stats["rights_blocked"] == 0
    assert len(client._queue) == 6  # 3件 × X+Threads
    for q in client._queue:
        assert q.get("rights_review_required") == "true"


def t_batch_not_allowed_all_blocked():
    client = MockSheetsClient()
    candidates = [_make_candidate(rights_status="not_allowed") for _ in range(2)]
    acc = {"account_id": "night_scout"}
    stats = generate_from_clips_batch(candidates, client, acc, mock_llm=True, dry_run=False)
    assert stats["rights_blocked"] == 2
    assert len(client._queue) == 0


_test("_needs_rights_review: unknown → True", t_needs_rights_review_unknown)
_test("_needs_rights_review: allowed → False", t_needs_rights_review_allowed)
_test("_needs_rights_review: not_allowed → False", t_needs_rights_review_not_allowed)
_test("_is_rights_blocked: unknown → False (Phase 2.28)", t_rights_blocked_unknown_is_false)
_test("_is_rights_blocked: not_allowed → True", t_rights_blocked_not_allowed_is_true)
_test("_is_rights_blocked: high_risk → True", t_rights_blocked_high_risk_is_true)
_test("save_clip_gen: unknown → rights_review_required=true", t_save_clip_gen_unknown_sets_rights_review_required)
_test("save_clip_gen: allowed → rights_review_required=false", t_save_clip_gen_allowed_no_rights_review_required)
_test("save_clip_gen: generation_mode=video_clip_reference", t_save_clip_gen_generation_mode_video_clip_reference)
_test("save_clip_gen: queue に source フィールド", t_save_clip_gen_queue_has_source_fields)


# ============================================================
# Phase 2.26: video_downloader
# ============================================================

print("\n=== Phase 2.26: video_downloader ===")


def t_extract_video_id_youtube():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _extract_video_id(url) == "dQw4w9WgXcQ"


def t_extract_video_id_youtu_be():
    url = "https://youtu.be/dQw4w9WgXcQ"
    assert _extract_video_id(url) == "dQw4w9WgXcQ"


def t_extract_video_id_shorts():
    url = "https://www.youtube.com/shorts/abc123xyz45"
    assert _extract_video_id(url) == "abc123xyz45"


def t_extract_video_id_unknown():
    url = "https://tiktok.com/@user/video/123456"
    assert _extract_video_id(url) == ""


def t_download_video_dry_run_success():
    post = _make_reference_post()
    result = download_video(post, dry_run=True)
    assert result.success is True
    assert result.reference_post_id == post["id"]


def t_download_video_no_confirm_is_dry():
    post = _make_reference_post()
    result = download_video(post, dry_run=False, confirm_download=False)
    assert result.success is True, "confirm_download=False は dry 扱い"


def t_download_video_empty_url_fails():
    post = _make_reference_post(video_url="")
    result = download_video(post, dry_run=True)
    assert result.success is False
    assert result.error != ""


def t_download_video_tiktok_dry_run_planning():
    # Phase 2.29: TikTok は dry_run=True で planning として success=True を返す
    post = _make_reference_post(platform="tiktok", video_url="https://tiktok.com/@user/video/123")
    result = download_video(post, dry_run=True)
    assert result.success is True, "dry-run TikTok は planning として成功扱い"
    assert "TikTok" in result.error


def t_download_video_tiktok_real_fails():
    # TikTok の実ダウンロードは未対応
    post = _make_reference_post(platform="tiktok", video_url="https://tiktok.com/@user/video/123")
    result = download_video(post, dry_run=False, confirm_download=True)
    assert result.success is False
    assert "TikTok" in result.error


def t_download_videos_batch_dry_run():
    posts = [_make_reference_post() for _ in range(3)]
    results = download_videos_batch(posts, dry_run=True)
    assert len(results) == 3
    assert all(r.success for r in results)


_test("_extract_video_id: youtube.com", t_extract_video_id_youtube)
_test("_extract_video_id: youtu.be", t_extract_video_id_youtu_be)
_test("_extract_video_id: shorts", t_extract_video_id_shorts)
_test("_extract_video_id: unknown → ''", t_extract_video_id_unknown)
_test("download_video: dry_run=True 成功", t_download_video_dry_run_success)
_test("download_video: confirm_download=False は dry 扱い", t_download_video_no_confirm_is_dry)
_test("download_video: empty URL → 失敗", t_download_video_empty_url_fails)
_test("download_video: TikTok dry-run → planning 成功（Phase 2.29）", t_download_video_tiktok_dry_run_planning)
_test("download_video: TikTok 実ダウンロード → 失敗", t_download_video_tiktok_real_fails)
_test("download_videos_batch: dry_run 3件", t_download_videos_batch_dry_run)


# ============================================================
# Phase 2.26: audio_extractor
# ============================================================

print("\n=== Phase 2.26: audio_extractor ===")


def t_extract_audio_dry_run_success():
    result = extract_audio(
        "/path/to/video.mp4",
        "ref-001",
        "night_scout",
        dry_run=True,
    )
    assert result.success is True
    assert result.reference_post_id == "ref-001"


def t_extract_audio_no_confirm_is_dry():
    result = extract_audio(
        "/path/to/video.mp4",
        "ref-001",
        "night_scout",
        dry_run=False,
        confirm_extract=False,
    )
    assert result.success is True


def t_extract_audio_missing_file_fails():
    result = extract_audio(
        "/nonexistent/file.mp4",
        "ref-001",
        "night_scout",
        dry_run=False,
        confirm_extract=True,
    )
    assert result.success is False
    assert result.error != ""


def t_extract_audio_output_path_has_wav():
    result = extract_audio(
        "/path/to/myvideo.mp4",
        "ref-001",
        "night_scout",
        output_dir="downloads/audio",
        dry_run=True,
    )
    assert result.local_audio_path.endswith(".wav")


def t_extract_audio_batch_dry_run():
    video_map = [
        {"reference_post_id": f"ref-{i}", "account_id": "night_scout", "local_path": f"/path/v{i}.mp4"}
        for i in range(3)
    ]
    results = extract_audio_batch(video_map, dry_run=True)
    assert len(results) == 3
    assert all(r.success for r in results)


_test("extract_audio: dry_run=True 成功", t_extract_audio_dry_run_success)
_test("extract_audio: confirm_extract=False は dry 扱い", t_extract_audio_no_confirm_is_dry)
_test("extract_audio: 存在しないファイル → 失敗", t_extract_audio_missing_file_fails)
_test("extract_audio: 出力パスが .wav", t_extract_audio_output_path_has_wav)
_test("extract_audio_batch: dry_run 3件", t_extract_audio_batch_dry_run)


# ============================================================
# Phase 2.25: run_video_pipeline ステップ関数
# ============================================================

print("\n=== Phase 2.25: run_video_pipeline ===")


def t_pipeline_step_sources_empty():
    from run_video_pipeline import step_sources
    client = MockSheetsClient()
    result = step_sources(client, "night_scout")
    assert "source_count" in result


def t_pipeline_step_collect_empty():
    from run_video_pipeline import step_collect
    client = MockSheetsClient()
    result = step_collect(client, "night_scout")
    assert "video_count" in result
    assert "pending_count" in result


def t_pipeline_step_cut_empty():
    from run_video_pipeline import step_cut
    client = MockSheetsClient()
    result = step_cut(client, "night_scout", dry_run=True)
    assert "cut" in result


def t_pipeline_step_generate_empty():
    from run_video_pipeline import step_generate
    client = MockSheetsClient()
    result = step_generate(client, "night_scout", dry_run=True, mock_llm=True)
    assert "generated" in result


def t_pipeline_step_integrity():
    from run_video_pipeline import step_integrity
    result = step_integrity("night_scout")
    assert "issues" in result


_test("pipeline step_sources: 空は正常", t_pipeline_step_sources_empty)
_test("pipeline step_collect: 空は正常", t_pipeline_step_collect_empty)
_test("pipeline step_cut: 空は正常", t_pipeline_step_cut_empty)
_test("pipeline step_generate: 空は正常", t_pipeline_step_generate_empty)
_test("pipeline step_integrity: 実行できる", t_pipeline_step_integrity)


# ============================================================
# check_pipeline_integrity Phase 2.28 拡張チェック
# ============================================================

print("\n=== check_pipeline_integrity Phase 2.28 拡張チェック ===")

from check_pipeline_integrity import check_queue_rights_gate, check_queue_text_policy


def t_integrity_queue_rights_gate_empty():
    client = MockSheetsClient()
    results: list[str] = []
    issues = check_queue_rights_gate(client, "night_scout", results)
    assert issues == 0


def t_integrity_queue_rights_gate_detects_violation():
    client = MockSheetsClient()
    # rights_review_required=true かつ READY は違反
    client._queue = [{
        "queue_id": "q-test-001",
        "account_id": "night_scout",
        "status": "READY",
        "platform": "x",
        "rights_review_required": "true",
        "rights_status": "unknown",
        "media_reuse_risk": "low",
    }]
    results: list[str] = []
    issues = check_queue_rights_gate(client, "night_scout", results)
    assert issues > 0


def t_integrity_queue_rights_gate_not_allowed():
    client = MockSheetsClient()
    client._queue = [{
        "queue_id": "q-test-002",
        "account_id": "night_scout",
        "status": "WAITING_REVIEW",
        "platform": "x",
        "rights_status": "not_allowed",
        "media_reuse_risk": "low",
    }]
    results: list[str] = []
    issues = check_queue_rights_gate(client, "night_scout", results)
    assert issues > 0, "not_allowed が queue に存在する場合は WARN"


def t_integrity_queue_text_policy_empty():
    client = MockSheetsClient()
    results: list[str] = []
    issues = check_queue_text_policy(client, "night_scout", results)
    assert issues == 0


def t_integrity_queue_text_policy_x_fail():
    client = MockSheetsClient()
    client._queue = [{
        "queue_id": "q-test-003",
        "account_id": "night_scout",
        "status": "WAITING_REVIEW",
        "platform": "x",
        "text_policy_status": "FAIL",
    }]
    results: list[str] = []
    issues = check_queue_text_policy(client, "night_scout", results)
    assert issues > 0


_test("integrity: queue_rights_gate 空は PASS", t_integrity_queue_rights_gate_empty)
_test("integrity: queue_rights_gate rights_review+READY は違反", t_integrity_queue_rights_gate_detects_violation)
_test("integrity: queue_rights_gate not_allowed は違反", t_integrity_queue_rights_gate_not_allowed)
_test("integrity: queue_text_policy 空は PASS", t_integrity_queue_text_policy_empty)
_test("integrity: queue_text_policy X FAIL は検出", t_integrity_queue_text_policy_x_fail)


# ============================================================
# フィクスチャ読み込みテスト
# ============================================================

print("\n=== フィクスチャ (Phase 2.25-2.28) ===")

FIXTURES_DIR = os.path.join(_V2_ROOT, "tests", "fixtures")


def t_fixture_video_downloader_result():
    path = os.path.join(FIXTURES_DIR, "sample_video_downloader_result.json")
    assert os.path.isfile(path), "sample_video_downloader_result.json が存在すること"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) > 0
    for r in data["results"]:
        assert "reference_post_id" in r
        assert "success" in r


def t_fixture_audio_extractor_result():
    path = os.path.join(FIXTURES_DIR, "sample_audio_extractor_result.json")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "results" in data
    for r in data["results"]:
        assert "reference_post_id" in r
        assert "local_audio_path" in r


def t_fixture_pipeline_run_result():
    path = os.path.join(FIXTURES_DIR, "sample_pipeline_run_result.json")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "results" in data
    assert "status" in data
    assert data["status"] == "OK"
    for step in ["sources", "collect", "transcribe", "analyze", "cut", "generate", "integrity"]:
        assert step in data["results"], f"ステップ {step!r} が results にない"


_test("fixture: sample_video_downloader_result.json", t_fixture_video_downloader_result)
_test("fixture: sample_audio_extractor_result.json", t_fixture_audio_extractor_result)
_test("fixture: sample_pipeline_run_result.json", t_fixture_pipeline_run_result)


# ============================================================
# 結果集計
# ============================================================

print("\n" + "=" * 60)
total = len(_results)
passed = sum(1 for s, _ in _results if s == PASS)
failed = sum(1 for s, _ in _results if s == FAIL)
print(f"テスト結果: {passed} PASS / {failed} FAIL / {total} 件")
if failed > 0:
    print("\n[FAIL 一覧]")
    for status, name in _results:
        if status == FAIL:
            print(f"  FAIL: {name}")
    sys.exit(1)
else:
    print("全テスト PASS")
    sys.exit(0)
