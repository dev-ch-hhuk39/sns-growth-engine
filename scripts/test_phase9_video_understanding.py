#!/usr/bin/env python3
"""test_phase9_video_understanding.py"""
from __future__ import annotations
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))

def main():
    print("=== Phase 9: Video Understanding テスト ===\n")

    from src.video.video_understanding import VideoUnderstanding
    from src.video.clip_candidate_planner import ClipCandidatePlanner

    vu = VideoUnderstanding()
    cp = ClipCandidatePlanner()

    item_with_transcript = {
        "source_id": "yt_001",
        "source_platform": "youtube",
        "post_url": "https://youtube.com/watch?v=mock",
        "title": "ライバーが月収100万円を超えた方法",
        "description": "配信者が稼ぐコツを解説します",
        "transcript": "今日は配信で稼ぐ方法をお伝えします。まず大切なのは毎日配信すること。次に視聴者との絡みを大切にすること。そして継続することが重要です。",
        "duration_seconds": 600.0,
        "view_count": 50000,
        "like_count": 2000,
    }

    item_no_transcript = {
        "source_id": "yt_002",
        "source_platform": "youtube",
        "post_url": "https://youtube.com/watch?v=mock2",
        "title": "transcript なし動画",
        "description": "説明文のみ",
        "transcript": None,
        "duration_seconds": 300.0,
        "view_count": 10000,
        "like_count": 500,
    }

    # transcript あり - mock
    print("[1] transcript あり (mock)")
    result_m = vu.analyze(item_with_transcript, account_id="liver_manager",
                          target_platform="threads", mock=True)
    check("mock status=OK", result_m["status"] == "OK")
    check("mock flag", result_m.get("mock") is True)
    check("key_points あり", len(result_m.get("key_points", [])) > 0)
    check("hook_candidates あり", len(result_m.get("hook_candidates", [])) > 0)
    check("clip_candidates あり", len(result_m.get("clip_candidates", [])) > 0)
    check("generated_post_copy あり", result_m.get("generated_post_copy") is not None)
    check("generated_thread_copy あり", result_m.get("generated_thread_copy") is not None)
    check("実download=False", result_m["media_ingestion_plan"].get("download_required") is False)
    check("実cut=False", result_m["media_ingestion_plan"].get("cut_required") is False)
    check("実upload=False", result_m["media_ingestion_plan"].get("upload_required") is False)

    # transcript あり - 実計算
    print("\n[2] transcript あり (実計算)")
    result_r = vu.analyze(item_with_transcript, account_id="liver_manager",
                          target_platform="threads", mock=False)
    check("status=OK", result_r["status"] == "OK")
    check("has_transcript=True", result_r["has_transcript"] is True)
    check("key_points 抽出", len(result_r.get("key_points", [])) > 0)
    check("clip_candidates あり", len(result_r.get("clip_candidates", [])) > 0)
    for clip in result_r.get("clip_candidates", []):
        check(f"clip download_required=False", clip.get("download_required") is False)
        check(f"clip cut_required=False", clip.get("cut_required") is False)

    # transcript なし
    print("\n[3] transcript なし → NOT_READY_TRANSCRIPT")
    result_no = vu.analyze(item_no_transcript, account_id="liver_manager",
                           target_platform="threads", mock=False)
    check("status=NOT_READY_TRANSCRIPT", result_no["status"] == "NOT_READY_TRANSCRIPT")
    check("has_transcript=False", result_no["has_transcript"] is False)
    check("transcript_required in media_plan",
          result_no["media_ingestion_plan"].get("transcript_required") is True)
    check("clip_candidates 空", result_no.get("clip_candidates") == [])

    # ClipCandidatePlanner
    print("\n[4] ClipCandidatePlanner (mock)")
    plan_m = cp.plan(result_m, account_id="liver_manager",
                     target_platform="threads", mock=True)
    check("plan status=OK", plan_m["status"] == "OK")
    check("planned_clips > 0", plan_m.get("planned_clips", 0) > 0)
    check("clips リスト", isinstance(plan_m.get("clips"), list))

    # ClipCandidatePlanner - 実データ
    print("\n[5] ClipCandidatePlanner (実データ)")
    plan_r = cp.plan(result_r, account_id="liver_manager",
                     target_platform="threads", mock=False)
    check("plan status=OK", plan_r["status"] == "OK")
    for clip in plan_r.get("clips", []):
        check("clip media_plan action=plan_only",
              clip["media_plan"]["action"] == "plan_only")
        check("clip download_required=False",
              clip["media_plan"]["download_required"] is False)

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] Video Understanding テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
