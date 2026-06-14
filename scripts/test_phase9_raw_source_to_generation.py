#!/usr/bin/env python3
"""test_phase9_raw_source_to_generation.py"""
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
    print("=== Phase 9: raw_source_items → reference_posts / generation 接続テスト ===\n")

    from src.reference.fetchers.base_fetcher import RawSourceItem
    from src.reference.buzz_scorer import score_items, filter_top_items
    from src.video.video_understanding import VideoUnderstanding
    from src.generation.video_reference_generator import VideoReferenceGenerator
    from src.generation.original_hypothesis_generator import OriginalHypothesisGenerator

    # 1. raw_source_items 作成
    print("[1] raw_source_items 準備")
    items = [
        RawSourceItem(
            source_id="src_yt_001", source_platform="youtube",
            target_account_id="liver_manager",
            item_type="video", title="配信で稼ぐ方法",
            text="配信で稼ぐ方法を解説", like_count=2000, view_count=50000,
            video_urls=["https://youtube.com/mock"], mock=True,
        ),
        RawSourceItem(
            source_id="src_x_001", source_platform="x",
            target_account_id="night_scout",
            item_type="post", text="夜職から転職成功した話",
            like_count=1500, repost_count=200, mock=True,
        ),
    ]
    check("items 生成", len(items) == 2)

    # 2. buzz scoring
    print("\n[2] buzz scoring → top items 抽出")
    scored = score_items(items)
    top = filter_top_items(scored, min_buzz_score=0.0, top_n=2)
    check("scored 2件", len(scored) == 2)
    check("top items あり", len(top) >= 1)
    check("buzz_score 付与", all(i.buzz_score is not None for i in top))

    # 3. video_understanding
    print("\n[3] VideoUnderstanding (mock)")
    vu = VideoUnderstanding()
    yt_item = next((i for i in top if i.source_platform == "youtube"), top[0])
    understanding = vu.analyze(yt_item.to_dict(), account_id="liver_manager",
                               target_platform="threads", mock=True)
    check("understanding status=OK", understanding["status"] in ("OK", "NOT_READY_TRANSCRIPT"))
    check("title 保持", bool(understanding.get("title")))
    check("hook_candidates あり", len(understanding.get("hook_candidates", [])) > 0)
    check("clip_candidates 構造", isinstance(understanding.get("clip_candidates"), list))
    check("media_plan あり", "media_ingestion_plan" in understanding)
    check("実download=False", understanding["media_ingestion_plan"].get("download_required") is False)

    # 4. VideoReferenceGenerator
    print("\n[4] VideoReferenceGenerator (mock)")
    vg = VideoReferenceGenerator()
    gen_result = vg.generate(understanding, account_id="liver_manager",
                             target_platform="threads", mock=True)
    check("gen status", gen_result["status"] in ("PLANNED", "WAITING_REVIEW", "MOCK"))
    check("draft_count > 0", gen_result["draft_count"] > 0)
    check("drafts リスト", isinstance(gen_result["drafts"], list))

    # 5. beauty_account = WAITING_REVIEW
    print("\n[5] beauty_account → WAITING_REVIEW")
    gen_beauty = vg.generate(understanding, account_id="beauty_account",
                             target_platform="threads", mock=True)
    check("beauty status=WAITING_REVIEW", gen_beauty["status"] == "WAITING_REVIEW")
    check("beauty is_beauty=True", gen_beauty["is_beauty"] is True)

    # 6. OriginalHypothesisGenerator
    print("\n[6] OriginalHypothesisGenerator (mock)")
    ohg = OriginalHypothesisGenerator()
    hyp_result = ohg.generate(
        "night_scout", platform="x",
        topic="夜職転職のコツ", count=3, mock=True,
    )
    check("ohg job_id あり", bool(hyp_result.get("job_id")))
    check("ohg draft_count=3", hyp_result["draft_count"] == 3)
    check("ohg status=PLANNED", hyp_result["status"] == "PLANNED")

    hyp_beauty = ohg.generate("beauty_account", platform="threads", count=2, mock=True)
    check("beauty ohg WAITING_REVIEW", hyp_beauty["status"] == "WAITING_REVIEW")

    # 7. DRY_RUN
    print("\n[7] dry_run=True → DRY_RUN")
    hyp_dry = ohg.generate("night_scout", platform="x", mock=False, dry_run=True)
    check("dry_run status=DRY_RUN", hyp_dry["status"] == "DRY_RUN")
    check("dry_run draft_count=0", hyp_dry["draft_count"] == 0)

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] raw_source_items → generation 接続テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
