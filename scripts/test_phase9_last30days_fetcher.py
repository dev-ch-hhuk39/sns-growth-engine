#!/usr/bin/env python3
"""test_phase9_last30days_fetcher.py"""
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
    print("=== Phase 9: Last30Days Fetcher テスト ===\n")

    from src.reference.fetchers.last30days_fetcher import Last30DaysFetcher
    fetcher = Last30DaysFetcher()

    src = {
        "source_id": "trend_001",
        "source_platform": "x",
        "source_handle": "夜職スカウト",
        "collection_method": "last30days_skill",
    }

    print("[1] アダプター属性")
    check("adapter_name", fetcher.adapter_name == "last30days_skill")
    check("x in supported_platforms", "x" in fetcher.supported_platforms)

    print("\n[2] モック取得")
    result = fetcher.fetch(src, target_account_id="night_scout", mock=True)
    check("mock status=OK", result.status == "OK")
    check("mock items > 0", len(result.items) > 0)
    check("item_type=trend_insight", all(i.item_type == "trend_insight" for i in result.items))
    check("recommended_generation_mode", all(
        i.recommended_generation_mode == "original_hypothesis" for i in result.items
    ))

    print("\n[3] trend_insights の内容確認")
    if result.items:
        item = result.items[0]
        check("text あり", bool(item.text))
        check("why_it_grew あり", item.why_it_grew is not None)

    print("\n[4] confirm_fetch なし = BLOCKED")
    result_blocked = fetcher.fetch(src, mock=False, confirm_fetch=False)
    check("BLOCKED", result_blocked.status == "BLOCKED")

    print("\n[5] 未インストール = NOT_INSTALLED")
    result_ni = fetcher.fetch(src, mock=False, confirm_fetch=True)
    check("NOT_INSTALLED or ERROR", result_ni.status in ("NOT_INSTALLED", "ERROR"))
    print("  [INFO] last30days-skill 未インストール。NOT_INSTALLED として正常。")

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] Last30Days Fetcher テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
