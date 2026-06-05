"""
test_phase221_224.py - Phase 2.21-2.24 テストスイート

テスト範囲:
  2.21: clip_candidate_analyzer（分析・正規化・バッチ・保存）
  2.22: clip_cutter（時間変換・出力パス・dry-run・ffmpeg-guard・batch）
  2.23: media_assets / drafts / social_derivatives / queue スキーマ検証
  2.24: video_clip_generator（権利ゲート・WAITING_REVIEW・テキストポリシー・バッチ）
  共通: MockSheetsClient video_clip_candidates / video_transcripts CRUD
  CLI:  transcribe_videos 新フラグ / check_pipeline_integrity video_clip チェック
"""
from __future__ import annotations

import json
import os
import sys
import uuid

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))
sys.path.insert(0, os.path.join(_V2_ROOT, "scripts"))

from sheets_client import MockSheetsClient, TAB_DEFINITIONS
from video.clip_candidate_analyzer import (
    analyze_transcript,
    analyze_transcripts_batch,
    save_clip_candidates,
    MOCK_CLIP_CANDIDATES,
    _normalize_candidate,
)
from video.clip_cutter import (
    ClipCutResult,
    _parse_time_to_seconds,
    _build_output_path,
    cut_clip,
    cut_clips_batch,
    update_cut_status,
)
from generation.video_clip_generator import (
    _is_rights_blocked,
    generate_from_clip,
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


# ============================================================
# ヘルパー: モックデータ
# ============================================================

def _make_transcript(**kwargs) -> dict:
    base = {
        "transcript_id": f"tr-{str(uuid.uuid4())[:8]}",
        "account_id": "night_scout",
        "reference_post_id": "ref-yt-test",
        "source_platform": "youtube",
        "video_url": "https://www.youtube.com/watch?v=test",
        "transcription_status": "done",
        "duration_seconds": 600,
        "segments_json": '[{"start":0,"end":60,"text":"テスト"}]',
    }
    base.update(kwargs)
    return base


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


def _make_account(**kwargs) -> dict:
    base = {
        "account_id": "night_scout",
        "account_name": "夜職スカウト",
        "target_persona": "20代夜職女性",
    }
    base.update(kwargs)
    return base


# ============================================================
# Phase 2.21: clip_candidate_analyzer
# ============================================================

print("\n=== Phase 2.21: clip_candidate_analyzer ===")


def t_analyze_transcript_mock_returns_list():
    tr = _make_transcript()
    result = analyze_transcript(tr, "night_scout", n_candidates=6, mock_llm=True)
    assert isinstance(result, list), "list が返ること"
    assert len(result) > 0, "候補が1件以上"


def t_analyze_transcript_mock_n_candidates():
    tr = _make_transcript()
    result = analyze_transcript(tr, "night_scout", n_candidates=3, mock_llm=True)
    assert len(result) == 3, f"n_candidates=3 のとき3件 (got {len(result)})"


def t_analyze_transcript_mock_required_keys():
    tr = _make_transcript()
    result = analyze_transcript(tr, "night_scout", mock_llm=True)
    required = [
        "clip_id", "account_id", "reference_post_id", "transcript_id",
        "start_time", "end_time", "duration_seconds",
        "clip_title", "hook", "clip_status",
        "rights_status", "permission_status",
        "confidence_score", "cut_status", "text_generation_status",
    ]
    for k in required:
        assert k in result[0], f"キー '{k}' がない"


def t_analyze_transcript_sets_account_id():
    tr = _make_transcript(account_id="liver_manager")
    result = analyze_transcript(tr, "liver_manager", mock_llm=True)
    for c in result:
        assert c["account_id"] == "liver_manager", "account_id がセットされること"


def t_analyze_transcript_sets_transcript_id():
    tr = _make_transcript(transcript_id="tr-special-id")
    result = analyze_transcript(tr, "night_scout", mock_llm=True)
    for c in result:
        assert c["transcript_id"] == "tr-special-id", "transcript_id が引き継がれること"


def t_analyze_transcript_clip_status_candidate():
    tr = _make_transcript()
    result = analyze_transcript(tr, "night_scout", mock_llm=True)
    for c in result:
        assert c["clip_status"] == "candidate", "clip_status=candidate"


def t_analyze_transcript_cut_status_pending():
    tr = _make_transcript()
    result = analyze_transcript(tr, "night_scout", mock_llm=True)
    for c in result:
        assert c["cut_status"] == "pending", "cut_status=pending"


def t_analyze_transcript_text_gen_status_pending():
    tr = _make_transcript()
    result = analyze_transcript(tr, "night_scout", mock_llm=True)
    for c in result:
        assert c["text_generation_status"] == "pending", "text_generation_status=pending"


def t_analyze_transcripts_batch():
    trs = [_make_transcript() for _ in range(3)]
    result = analyze_transcripts_batch(trs, "night_scout", n_candidates=2, mock_llm=True)
    assert len(result) == 6, f"3件 × 2候補 = 6 (got {len(result)})"


def t_save_clip_candidates_dry_run():
    client = MockSheetsClient()
    candidates = [_make_candidate() for _ in range(3)]
    stats = save_clip_candidates(client, candidates, dry_run=True)
    assert stats["added"] == 0, "dry_run=True は added=0"
    assert stats["skipped"] == 3, "dry_run=True は skipped=3"


def t_save_clip_candidates_mock_write():
    client = MockSheetsClient()
    candidates = [_make_candidate() for _ in range(2)]
    stats = save_clip_candidates(client, candidates, dry_run=False)
    assert stats["added"] == 2, f"2件保存 (got {stats['added']})"
    stored = client.get_video_clip_candidates(account_id="night_scout")
    assert len(stored) == 2, "MockSheetsClient に2件保存"


_test("analyze_transcript mock list返却", t_analyze_transcript_mock_returns_list)
_test("analyze_transcript n_candidates=3", t_analyze_transcript_mock_n_candidates)
_test("analyze_transcript 必須キー確認", t_analyze_transcript_mock_required_keys)
_test("analyze_transcript account_id セット", t_analyze_transcript_sets_account_id)
_test("analyze_transcript transcript_id 引き継ぎ", t_analyze_transcript_sets_transcript_id)
_test("analyze_transcript clip_status=candidate", t_analyze_transcript_clip_status_candidate)
_test("analyze_transcript cut_status=pending", t_analyze_transcript_cut_status_pending)
_test("analyze_transcript text_gen_status=pending", t_analyze_transcript_text_gen_status_pending)
_test("analyze_transcripts_batch 3×2=6件", t_analyze_transcripts_batch)
_test("save_clip_candidates dry_run", t_save_clip_candidates_dry_run)
_test("save_clip_candidates mock書き込み", t_save_clip_candidates_mock_write)


# ============================================================
# Phase 2.22: clip_cutter
# ============================================================

print("\n=== Phase 2.22: clip_cutter ===")


def t_parse_time_hhmmss():
    assert _parse_time_to_seconds("00:01:30") == 90
    assert _parse_time_to_seconds("00:00:00") == 0
    assert _parse_time_to_seconds("01:00:00") == 3600


def t_parse_time_mmss():
    assert _parse_time_to_seconds("1:30") == 90
    assert _parse_time_to_seconds("0:45") == 45


def t_parse_time_invalid():
    assert _parse_time_to_seconds("invalid") == 0
    assert _parse_time_to_seconds("") == 0


def t_cut_clip_dry_run_success():
    c = _make_candidate(start_time="00:01:00", end_time="00:02:00")
    result = cut_clip(c, "dummy.mp4", dry_run=True)
    assert result.success is True
    assert result.clip_id == c["clip_id"]
    assert result.duration_seconds == 60


def t_cut_clip_no_confirm_cut_is_dry():
    c = _make_candidate(start_time="00:01:00", end_time="00:02:30")
    result = cut_clip(c, "dummy.mp4", dry_run=False, confirm_cut=False)
    assert result.success is True, "confirm_cut=False は dry_run 扱い"
    assert result.duration_seconds == 90


def t_cut_clip_missing_source_fails():
    c = _make_candidate()
    result = cut_clip(c, "/nonexistent/file.mp4", dry_run=False, confirm_cut=True)
    assert result.success is False, "存在しないソースファイルは失敗"
    assert result.error != ""


def t_cut_clips_batch_dry_run():
    candidates = [_make_candidate() for _ in range(3)]
    results = cut_clips_batch(candidates, {}, dry_run=True)
    assert len(results) == 3
    assert all(r.success for r in results)


def t_update_cut_status_dry_run():
    client = MockSheetsClient()
    results = [
        ClipCutResult(clip_id="clip-a", success=True, local_clip_path="/clips/clip-a.mp4"),
        ClipCutResult(clip_id="clip-b", success=False, error="ffmpeg not found"),
    ]
    stats = update_cut_status(client, results, dry_run=True)
    assert stats["skipped"] == 2
    assert stats["updated"] == 0


def t_update_cut_status_mock_write():
    client = MockSheetsClient()
    c = _make_candidate()
    client.save_video_clip_candidate(c)
    results = [ClipCutResult(clip_id=c["clip_id"], success=True, local_clip_path="/clips/test.mp4")]
    stats = update_cut_status(client, results, dry_run=False)
    assert stats["updated"] == 1
    stored = client.find_video_clip_candidate_by_clip_id(c["clip_id"])
    assert stored is not None and stored.get("cut_status") == "done"


_test("_parse_time_to_seconds HH:MM:SS", t_parse_time_hhmmss)
_test("_parse_time_to_seconds MM:SS", t_parse_time_mmss)
_test("_parse_time_to_seconds invalid", t_parse_time_invalid)
_test("cut_clip dry_run=True 成功", t_cut_clip_dry_run_success)
_test("cut_clip confirm_cut=False はdry扱い", t_cut_clip_no_confirm_cut_is_dry)
_test("cut_clip 存在しないソース失敗", t_cut_clip_missing_source_fails)
_test("cut_clips_batch dry_run 3件", t_cut_clips_batch_dry_run)
_test("update_cut_status dry_run skipped", t_update_cut_status_dry_run)
_test("update_cut_status mock write", t_update_cut_status_mock_write)


# ============================================================
# Phase 2.23: スキーマ検証（TAB_DEFINITIONS）
# ============================================================

print("\n=== Phase 2.23: スキーマ検証 ===")


def t_schema_video_clip_candidates_phase221_cols():
    cols = TAB_DEFINITIONS["video_clip_candidates"]
    for col in ["confidence_score", "cut_status", "local_clip_path",
                "clip_media_asset_id", "text_generation_status",
                "generated_draft_id", "generated_at"]:
        assert col in cols, f"video_clip_candidates に {col!r} がない"


def t_schema_media_assets_phase221_cols():
    cols = TAB_DEFINITIONS["media_assets"]
    for col in ["video_clip_id", "local_path", "rights_status",
                "permission_status", "aspect_ratio", "duration_seconds"]:
        assert col in cols, f"media_assets に {col!r} がない"


def t_schema_drafts_phase224_cols():
    cols = TAB_DEFINITIONS["drafts"]
    for col in ["media_asset_id", "video_clip_id", "source_video_url", "source_time_range"]:
        assert col in cols, f"drafts に {col!r} がない"


def t_schema_social_derivatives_phase224_cols():
    cols = TAB_DEFINITIONS["social_derivatives"]
    for col in ["video_clip_id", "source_time_range"]:
        assert col in cols, f"social_derivatives に {col!r} がない"


def t_schema_queue_phase224_cols():
    cols = TAB_DEFINITIONS["queue"]
    for col in ["video_clip_id", "rights_status", "permission_status"]:
        assert col in cols, f"queue に {col!r} がない"


def t_schema_queue_phase228_cols():
    cols = TAB_DEFINITIONS["queue"]
    for col in ["rights_review_required", "media_reuse_risk", "source_video_url", "source_time_range"]:
        assert col in cols, f"queue に Phase 2.28 列 {col!r} がない"


def t_schema_video_clip_candidates_phase228_cols():
    cols = TAB_DEFINITIONS["video_clip_candidates"]
    assert "rights_review_required" in cols, "video_clip_candidates に rights_review_required がない"


def t_schema_no_duplicate_cols():
    for tab, cols in TAB_DEFINITIONS.items():
        seen = set()
        for c in cols:
            assert c not in seen, f"{tab} に重複列: {c!r}"
            seen.add(c)


_test("video_clip_candidates Phase 2.21 列", t_schema_video_clip_candidates_phase221_cols)
_test("media_assets Phase 2.21 列", t_schema_media_assets_phase221_cols)
_test("drafts Phase 2.24 列", t_schema_drafts_phase224_cols)
_test("social_derivatives Phase 2.24 列", t_schema_social_derivatives_phase224_cols)
_test("queue Phase 2.24 列", t_schema_queue_phase224_cols)
_test("queue Phase 2.28 列", t_schema_queue_phase228_cols)
_test("video_clip_candidates Phase 2.28 列", t_schema_video_clip_candidates_phase228_cols)
_test("TAB_DEFINITIONS 重複列なし", t_schema_no_duplicate_cols)


# ============================================================
# Phase 2.24: video_clip_generator
# ============================================================

print("\n=== Phase 2.24: video_clip_generator ===")


def t_rights_blocked_unknown():
    # Phase 2.28: unknown は queue 追加可能（ブロックしない）
    c = _make_candidate(rights_status="unknown")
    assert _is_rights_blocked(c) is False


def t_rights_blocked_not_allowed():
    c = _make_candidate(rights_status="not_allowed")
    assert _is_rights_blocked(c) is True


def t_rights_blocked_allowed():
    c = _make_candidate(rights_status="allowed", permission_status="granted")
    assert _is_rights_blocked(c) is False


def t_rights_blocked_high_risk():
    c = _make_candidate(rights_status="allowed", media_reuse_risk="high")
    assert _is_rights_blocked(c) is True


def t_rights_blocked_medium_risk():
    c = _make_candidate(rights_status="allowed", media_reuse_risk="medium")
    assert _is_rights_blocked(c) is False


def t_generate_from_clip_mock_returns_dict():
    c = _make_candidate()
    acc = _make_account()
    result = generate_from_clip(c, acc, mock_llm=True)
    assert isinstance(result, dict)
    assert "x_text" in result
    assert "threads_text" in result
    assert "title" in result


def t_generate_from_clip_x_text_nonempty():
    c = _make_candidate()
    acc = _make_account()
    result = generate_from_clip(c, acc, mock_llm=True)
    assert len(result["x_text"]) > 0


def t_save_clip_gen_dry_run():
    client = MockSheetsClient()
    c = _make_candidate(rights_status="unknown")
    gen = {"x_text": "テストX", "threads_text": "テストThreads", "title": "テスト", "hypothesis": "test", "media_strategy": "none"}
    result = save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=True)
    assert "draft_id" in result
    assert isinstance(result["rights_blocked"], bool)


def t_save_clip_gen_unknown_rights_has_queue_with_review_flag():
    # Phase 2.28: unknown は queue に追加される（rights_review_required=true 付き）
    client = MockSheetsClient()
    c = _make_candidate(rights_status="unknown")
    gen = {"x_text": "テストX", "threads_text": "テストThreads", "title": "テスト", "hypothesis": "", "media_strategy": "none"}
    result = save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    assert result["rights_blocked"] is False, "Phase 2.28: unknown はブロックしない"
    assert result["rights_review_required"] is True, "rights_review_required=True"
    assert len(result["queue_ids"]) == 2, "x + threads = 2件のqueue"
    for q in client._queue:
        assert q.get("rights_review_required") == "true"


def t_save_clip_gen_not_allowed_no_queue():
    # not_allowed は完全ブロック
    client = MockSheetsClient()
    c = _make_candidate(rights_status="not_allowed")
    gen = {"x_text": "テストX", "threads_text": "テストThreads", "title": "テスト", "hypothesis": "", "media_strategy": "none"}
    result = save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    assert result["rights_blocked"] is True
    assert result["queue_ids"] == [], "not_allowed は queue なし"
    assert len(client._queue) == 0


def t_save_clip_gen_allowed_has_queue():
    client = MockSheetsClient()
    c = _make_candidate(rights_status="allowed", permission_status="granted", media_reuse_risk="low")
    gen = {"x_text": "テストX", "threads_text": "テストThreads", "title": "テスト", "hypothesis": "", "media_strategy": "none"}
    result = save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    assert result["rights_blocked"] is False
    assert len(result["queue_ids"]) == 2, "x + threads = 2件のqueue"


def t_save_clip_gen_queue_status_waiting_review():
    client = MockSheetsClient()
    c = _make_candidate(rights_status="allowed", permission_status="granted", media_reuse_risk="low")
    gen = {"x_text": "テストX", "threads_text": "テストThreads", "title": "テスト", "hypothesis": "", "media_strategy": "none"}
    save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    for q in client._queue:
        assert q["status"] == "WAITING_REVIEW", f"queue status は常に WAITING_REVIEW (got {q['status']})"


def t_save_clip_gen_updates_text_gen_status():
    client = MockSheetsClient()
    c = _make_candidate()
    client.save_video_clip_candidate(c)
    gen = {"x_text": "X", "threads_text": "Th", "title": "T", "hypothesis": "", "media_strategy": "none"}
    result = save_clip_generation_result(client, c, gen, account_id="night_scout", dry_run=False)
    stored = client.find_video_clip_candidate_by_clip_id(c["clip_id"])
    assert stored is not None and stored.get("text_generation_status") == "done"
    assert stored.get("generated_draft_id") == result["draft_id"]


def t_generate_from_clips_batch_unknown_rights_in_queue():
    # Phase 2.28: unknown はブロックしない → 全件 queue に追加
    client = MockSheetsClient()
    candidates = [_make_candidate(rights_status="unknown") for _ in range(3)]
    acc = _make_account()
    stats = generate_from_clips_batch(candidates, client, acc, mock_llm=True, dry_run=False)
    assert stats["total"] == 3
    assert stats["generated"] == 3
    assert stats["rights_blocked"] == 0, "Phase 2.28: unknown はブロックしない"
    assert len(client._queue) == 6, "3件 × X+Threads = 6件のqueue"
    for q in client._queue:
        assert q.get("rights_review_required") == "true"


def t_generate_from_clips_batch_not_allowed_blocked():
    # not_allowed は完全ブロック
    client = MockSheetsClient()
    candidates = [_make_candidate(rights_status="not_allowed") for _ in range(3)]
    acc = _make_account()
    stats = generate_from_clips_batch(candidates, client, acc, mock_llm=True, dry_run=False)
    assert stats["total"] == 3
    assert stats["rights_blocked"] == 3
    assert len(client._queue) == 0


def t_generate_from_clips_batch_mixed_rights():
    # Phase 2.28: unknown はブロックしない
    client = MockSheetsClient()
    candidates = [
        _make_candidate(rights_status="allowed", permission_status="granted", media_reuse_risk="low"),
        _make_candidate(rights_status="unknown"),
        _make_candidate(rights_status="not_allowed"),  # これだけブロック
    ]
    acc = _make_account()
    stats = generate_from_clips_batch(candidates, client, acc, mock_llm=True, dry_run=False)
    assert stats["rights_blocked"] == 1, "not_allowed の1件だけブロック"
    assert len(client._queue) == 4, "allowed×1 + unknown×1 = 2件 × X+Threads = 4件"


def t_generate_from_clips_batch_no_error():
    client = MockSheetsClient()
    candidates = [_make_candidate() for _ in range(5)]
    acc = _make_account()
    stats = generate_from_clips_batch(candidates, client, acc, mock_llm=True, dry_run=True)
    assert stats["errors"] == 0


_test("rights_blocked: unknown → False (Phase 2.28)", t_rights_blocked_unknown)
_test("rights_blocked: not_allowed → True", t_rights_blocked_not_allowed)
_test("rights_blocked: allowed+granted → False", t_rights_blocked_allowed)
_test("rights_blocked: high_risk → True", t_rights_blocked_high_risk)
_test("rights_blocked: medium_risk → False", t_rights_blocked_medium_risk)
_test("generate_from_clip mock dict返却", t_generate_from_clip_mock_returns_dict)
_test("generate_from_clip x_text 非空", t_generate_from_clip_x_text_nonempty)
_test("save_clip_gen dry_run", t_save_clip_gen_dry_run)
_test("save_clip_gen unknown → queue 2件 + rights_review_required", t_save_clip_gen_unknown_rights_has_queue_with_review_flag)
_test("save_clip_gen not_allowed → queue なし", t_save_clip_gen_not_allowed_no_queue)
_test("save_clip_gen allowed → queue 2件", t_save_clip_gen_allowed_has_queue)
_test("save_clip_gen queue status=WAITING_REVIEW", t_save_clip_gen_queue_status_waiting_review)
_test("save_clip_gen text_generation_status=done 更新", t_save_clip_gen_updates_text_gen_status)
_test("batch unknown全件 → queue 6件 rights_review_required", t_generate_from_clips_batch_unknown_rights_in_queue)
_test("batch not_allowed全件 → queue 0件", t_generate_from_clips_batch_not_allowed_blocked)
_test("batch mixed_rights → not_allwed のみブロック", t_generate_from_clips_batch_mixed_rights)
_test("batch エラー0件", t_generate_from_clips_batch_no_error)


# ============================================================
# MockSheetsClient CRUD: video_clip_candidates / transcripts
# ============================================================

print("\n=== MockSheetsClient CRUD: video pipeline ===")


def t_mock_save_video_clip_candidate_insert():
    client = MockSheetsClient()
    c = _make_candidate()
    result = client.save_video_clip_candidate(c)
    assert result is True
    stored = client.get_video_clip_candidates()
    assert len(stored) == 1


def t_mock_save_video_clip_candidate_upsert():
    client = MockSheetsClient()
    c = _make_candidate()
    client.save_video_clip_candidate(c)
    c2 = dict(c)
    c2["clip_title"] = "更新タイトル"
    client.save_video_clip_candidate(c2)
    all_clips = client.get_video_clip_candidates()
    assert len(all_clips) == 1, "upsert: 同clip_idは1件"
    assert all_clips[0]["clip_title"] == "更新タイトル"


def t_mock_find_video_clip_candidate_by_clip_id():
    client = MockSheetsClient()
    c = _make_candidate()
    client.save_video_clip_candidate(c)
    found = client.find_video_clip_candidate_by_clip_id(c["clip_id"])
    assert found is not None
    assert found["clip_id"] == c["clip_id"]


def t_mock_find_video_clip_candidate_not_found():
    client = MockSheetsClient()
    found = client.find_video_clip_candidate_by_clip_id("nonexistent")
    assert found is None


def t_mock_update_video_clip_candidate():
    client = MockSheetsClient()
    c = _make_candidate()
    client.save_video_clip_candidate(c)
    ok = client.update_video_clip_candidate(c["clip_id"], cut_status="done", local_clip_path="/clips/test.mp4")
    assert ok is True
    stored = client.find_video_clip_candidate_by_clip_id(c["clip_id"])
    assert stored["cut_status"] == "done"
    assert stored["local_clip_path"] == "/clips/test.mp4"


def t_mock_get_video_clip_candidates_filter_account():
    client = MockSheetsClient()
    for aid in ["night_scout", "night_scout", "liver_manager"]:
        client.save_video_clip_candidate(_make_candidate(account_id=aid))
    result = client.get_video_clip_candidates(account_id="night_scout")
    assert len(result) == 2


def t_mock_get_video_clip_candidates_filter_clip_status():
    client = MockSheetsClient()
    client.save_video_clip_candidate(_make_candidate(clip_status="candidate"))
    client.save_video_clip_candidate(_make_candidate(clip_status="approved"))
    result = client.get_video_clip_candidates(clip_status="approved")
    assert len(result) == 1


def t_mock_get_video_clip_candidates_limit():
    client = MockSheetsClient()
    for _ in range(5):
        client.save_video_clip_candidate(_make_candidate())
    result = client.get_video_clip_candidates(limit=3)
    assert len(result) == 3


def t_mock_save_video_transcript_crud():
    client = MockSheetsClient()
    tr = _make_transcript()
    result = client.save_video_transcript(tr)
    assert result is True
    found = client.find_video_transcript_by_id(tr["transcript_id"])
    assert found is not None


def t_mock_get_video_transcripts_filter_status():
    client = MockSheetsClient()
    for status in ["done", "done", "pending", "failed"]:
        client.save_video_transcript(_make_transcript(
            transcript_id=f"tr-{str(uuid.uuid4())[:6]}",
            transcription_status=status
        ))
    done = client.get_video_transcripts(transcription_status="done")
    assert len(done) == 2


_test("MockSheetsClient: save_video_clip_candidate insert", t_mock_save_video_clip_candidate_insert)
_test("MockSheetsClient: save_video_clip_candidate upsert", t_mock_save_video_clip_candidate_upsert)
_test("MockSheetsClient: find by clip_id 存在", t_mock_find_video_clip_candidate_by_clip_id)
_test("MockSheetsClient: find by clip_id 不存在", t_mock_find_video_clip_candidate_not_found)
_test("MockSheetsClient: update_video_clip_candidate", t_mock_update_video_clip_candidate)
_test("MockSheetsClient: get filter by account_id", t_mock_get_video_clip_candidates_filter_account)
_test("MockSheetsClient: get filter by clip_status", t_mock_get_video_clip_candidates_filter_clip_status)
_test("MockSheetsClient: get limit", t_mock_get_video_clip_candidates_limit)
_test("MockSheetsClient: video_transcript CRUD", t_mock_save_video_transcript_crud)
_test("MockSheetsClient: get_video_transcripts filter status", t_mock_get_video_transcripts_filter_status)


# ============================================================
# フィクスチャ読み込みテスト
# ============================================================

print("\n=== フィクスチャ ===")

FIXTURES_DIR = os.path.join(_V2_ROOT, "tests", "fixtures")


def t_fixture_sample_video_transcript_exists():
    path = os.path.join(FIXTURES_DIR, "sample_video_transcript.json")
    assert os.path.isfile(path), "sample_video_transcript.json が存在すること"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "transcript_id" in data
    assert "segments_json" in data
    assert data["transcription_status"] == "done"


def t_fixture_sample_video_clip_candidates_exists():
    path = os.path.join(FIXTURES_DIR, "sample_video_clip_candidates.json")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == 6, f"6件 (got {len(data)})"
    for c in data:
        assert "clip_id" in c
        assert "rights_status" in c
        assert "confidence_score" in c


def t_fixture_sample_video_clip_generation_response_exists():
    path = os.path.join(FIXTURES_DIR, "sample_video_clip_generation_response.json")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "generation" in data
    assert "x_text" in data["generation"]
    assert "threads_text" in data["generation"]


def t_fixture_rights_status_variety():
    path = os.path.join(FIXTURES_DIR, "sample_video_clip_candidates.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rights_values = {c["rights_status"] for c in data}
    assert "unknown" in rights_values, "unknown な候補が含まれること"
    assert "allowed" in rights_values, "allowed な候補が含まれること"


def t_fixture_media_reuse_risk_variety():
    path = os.path.join(FIXTURES_DIR, "sample_video_clip_candidates.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    risks = {c["media_reuse_risk"] for c in data}
    assert "high" in risks, "high_risk な候補が含まれること"
    assert "low" in risks


_test("fixture: sample_video_transcript.json", t_fixture_sample_video_transcript_exists)
_test("fixture: sample_video_clip_candidates.json 6件", t_fixture_sample_video_clip_candidates_exists)
_test("fixture: sample_video_clip_generation_response.json", t_fixture_sample_video_clip_generation_response_exists)
_test("fixture: rights_status のバリエーション", t_fixture_rights_status_variety)
_test("fixture: media_reuse_risk のバリエーション", t_fixture_media_reuse_risk_variety)


# ============================================================
# check_pipeline_integrity: video clip チェック
# ============================================================

print("\n=== check_pipeline_integrity: video clip checks ===")

sys.path.insert(0, os.path.join(_V2_ROOT, "scripts"))
from check_pipeline_integrity import (
    check_video_clip_candidates,
    check_video_transcripts,
    VALID_CLIP_STATUSES,
    VALID_CUT_STATUSES,
    VALID_TRANSCRIPTION_STATUSES,
)


def t_integrity_video_clip_empty():
    client = MockSheetsClient()
    results = []
    issues = check_video_clip_candidates(client, "night_scout", results)
    assert issues == 0
    assert any("空" in r for r in results)


def t_integrity_video_transcript_empty():
    client = MockSheetsClient()
    results = []
    issues = check_video_transcripts(client, "night_scout", results)
    assert issues == 0


def t_integrity_valid_clip_statuses():
    for s in ["candidate", "approved", "rejected", ""]:
        assert s in VALID_CLIP_STATUSES, f"{s!r} が VALID_CLIP_STATUSES にない"


def t_integrity_valid_cut_statuses():
    for s in ["pending", "cutting", "done", "failed", ""]:
        assert s in VALID_CUT_STATUSES, f"{s!r} が VALID_CUT_STATUSES にない"


def t_integrity_valid_transcription_statuses():
    for s in ["pending", "processing", "done", "failed", "skipped", ""]:
        assert s in VALID_TRANSCRIPTION_STATUSES, f"{s!r} が VALID_TRANSCRIPTION_STATUSES にない"


_test("integrity: video_clip_candidates 空は PASS", t_integrity_video_clip_empty)
_test("integrity: video_transcripts 空は PASS", t_integrity_video_transcript_empty)
_test("integrity: VALID_CLIP_STATUSES", t_integrity_valid_clip_statuses)
_test("integrity: VALID_CUT_STATUSES", t_integrity_valid_cut_statuses)
_test("integrity: VALID_TRANSCRIPTION_STATUSES", t_integrity_valid_transcription_statuses)


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
