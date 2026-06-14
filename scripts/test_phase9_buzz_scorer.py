#!/usr/bin/env python3
"""test_phase9_buzz_scorer.py"""
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
    print("=== Phase 9: Buzz Scorer テスト ===\n")

    from src.reference.fetchers.base_fetcher import RawSourceItem
    from src.reference.buzz_scorer import score_items, filter_top_items, items_to_dicts

    # テストデータ: 高buzz vs 低buzz
    items = [
        RawSourceItem(
            source_id="src_001", source_platform="x",
            like_count=5000, view_count=50000, repost_count=500, bookmark_count=200,
            follower_count=10000, text="高バズ投稿", item_type="post",
        ),
        RawSourceItem(
            source_id="src_001", source_platform="x",
            like_count=10, view_count=100, repost_count=1,
            follower_count=10000, text="低バズ投稿", item_type="post",
        ),
        RawSourceItem(
            source_id="src_002", source_platform="youtube",
            like_count=3000, view_count=100000,
            item_type="video", title="人気動画",
        ),
        RawSourceItem(
            source_id="src_001", source_platform="x",
            like_count=1000, view_count=10000, image_urls=["https://example.com/img.jpg"],
            item_type="post", text="画像付き中バズ",
        ),
    ]

    print("[1] score_items() 基本動作")
    scored = score_items(items)
    check("scored 件数一致", len(scored) == 4)
    check("buzz_score 付与", all(i.buzz_score is not None for i in scored))
    check("buzz_score 0〜1範囲", all(0.0 <= (i.buzz_score or 0) <= 1.0 for i in scored))
    check("buzz_rank 付与", all(i.buzz_rank is not None for i in scored))
    check("is_top_post あり", any(i.is_top_post for i in scored))

    print("\n[2] スコア大小関係")
    high = next(i for i in scored if "高バズ" in i.text)
    low = next(i for i in scored if "低バズ" in i.text)
    check("高バズ > 低バズ", (high.buzz_score or 0) > (low.buzz_score or 0))
    check("高バズ スコア > 0.1", (high.buzz_score or 0) > 0.1)

    print("\n[3] why_it_grew / replay_tip")
    check("why_it_grew 付与", high.why_it_grew is not None)
    check("replay_tip 付与", high.replay_tip is not None)
    check("recommended_generation_mode 付与", high.recommended_generation_mode is not None)

    print("\n[4] filter_top_items()")
    top3 = filter_top_items(scored, min_buzz_score=0.0, top_n=3)
    check("top_n=3 で3件以下", len(top3) <= 3)

    top_high = filter_top_items(scored, min_buzz_score=0.5)
    check("min_buzz_score フィルタ動作", all((i.buzz_score or 0) >= 0.5 for i in top_high))

    print("\n[5] items_to_dicts()")
    dicts = items_to_dicts(scored)
    check("dicts 件数", len(dicts) == 4)
    check("buzz_score in dict", "buzz_score" in dicts[0])
    check("why_it_grew in dict", "why_it_grew" in dicts[0])

    print("\n[6] メトリクス不足の暫定スコア")
    sparse = RawSourceItem(
        source_id="src_003", source_platform="threads",
        like_count=0, view_count=0, text="メトリクスなし投稿",
    )
    scored_sparse = score_items([sparse])
    check("メトリクスなしでもスコア算出", scored_sparse[0].buzz_score is not None)
    check("スコアは0以上", (scored_sparse[0].buzz_score or 0) >= 0.0)

    print("\n[7] platform別スコアリング (YouTube)")
    yt_items = [i for i in scored if i.source_platform == "youtube"]
    check("YouTube item スコア付与", all(i.buzz_score is not None for i in yt_items))

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] Buzz Scorer テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
