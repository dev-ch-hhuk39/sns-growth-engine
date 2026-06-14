#!/usr/bin/env python3
"""test_phase10_original_hypothesis_generation.py"""
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
    print("=== Phase 10: Original Hypothesis Generation テスト ===\n")

    from src.generation.original_hypothesis_generator import OriginalHypothesisGenerator, ACCOUNT_TONES

    gen = OriginalHypothesisGenerator()

    print("[1] ACCOUNT_TONES 定義確認")
    check("night_scout tone", "night_scout" in ACCOUNT_TONES)
    check("liver_manager tone", "liver_manager" in ACCOUNT_TONES)
    check("beauty_account tone", "beauty_account" in ACCOUNT_TONES)

    for account_id in ["night_scout", "liver_manager", "beauty_account"]:
        print(f"\n[{account_id}] テスト")

        # mock
        result_mock = gen.generate(
            account_id, platform="x" if account_id == "night_scout" else "threads",
            topic="テストトピック", count=3, mock=True,
        )
        check(f"{account_id} mock job_id", bool(result_mock.get("job_id")))
        check(f"{account_id} mock draft_count=3", result_mock["draft_count"] == 3)
        check(f"{account_id} mock flag", result_mock.get("mock") is True)

        is_beauty = account_id == "beauty_account"
        expected_status = "WAITING_REVIEW" if is_beauty else "PLANNED"
        check(f"{account_id} status={expected_status}", result_mock["status"] == expected_status)
        check(f"{account_id} is_beauty={is_beauty}", result_mock["is_beauty"] == is_beauty)

        # safety_check
        safety = result_mock.get("safety_check", {})
        check(f"{account_id} safety_check あり", isinstance(safety, dict))
        if is_beauty:
            check(f"{account_id} beauty safety note", safety.get("is_beauty_account") is True)

    # thread_series テスト
    print("\n[thread_series] テスト")
    result_thread = gen.generate(
        "liver_manager", platform="threads",
        post_type="thread_series", topic="ライバー育成", count=2, mock=True,
    )
    check("thread_series draft_count", result_thread["draft_count"] == 2)
    for d in result_thread["drafts"]:
        check("thread_series post_count", "thread_posts" in d or "text" in d)

    # dry_run
    print("\n[dry_run] テスト")
    result_dry = gen.generate("night_scout", platform="x", mock=False, dry_run=True)
    check("dry_run status=DRY_RUN", result_dry["status"] == "DRY_RUN")
    check("dry_run draft_count=0", result_dry["draft_count"] == 0)

    # 実生成 (dry_run=False, mock=False)
    print("\n[実生成] テスト")
    result_real = gen.generate(
        "night_scout", platform="x",
        topic="夜職転職のコツ", count=2, mock=False, dry_run=False,
    )
    check("実生成 status=PLANNED", result_real["status"] == "PLANNED")
    check("実生成 draft_count=2", result_real["draft_count"] == 2)
    for d in result_real["drafts"]:
        check("実生成 draft status=DRAFT", d["status"] == "DRAFT")

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] Original Hypothesis Generation テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
