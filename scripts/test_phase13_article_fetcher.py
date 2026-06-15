#!/usr/bin/env python3
"""test_phase13_article_fetcher.py"""
from __future__ import annotations
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))


def _make_note_source():
    return {
        "source_id": "src_lm_note_test_001",
        "source_platform": "note",
        "source_url": "https://note.com/test_account",
        "source_handle": "test_account",
        "collection_method": "browser_export",
        "fetch_enabled": False,
        "allow_network_fetch": False,
        "rights_policy": "reference_only",
        "reuse_policy": "reference_only",
        "media_policy": "plan_only",
        "max_items_per_run": 5,
    }


def main():
    print("=== Phase 13: ArticleFetcher テスト ===\n")

    print("[1] Import")
    try:
        from src.reference.fetchers.article_fetcher import ArticleFetcher
        from src.reference.fetchers.base_fetcher import FetchResult, RawSourceItem
        check("import OK", True)
    except Exception as e:
        check("import", False, str(e))
        sys.exit(1)

    fetcher = ArticleFetcher()
    source = _make_note_source()

    print("\n[2] adapter_name / supported_platforms")
    check("adapter_name=article_fetcher", fetcher.adapter_name == "article_fetcher")
    check("note in supported_platforms", "note" in fetcher.supported_platforms)
    check("article in supported_platforms", "article" in fetcher.supported_platforms)

    print("\n[3] mock=True (安全なデフォルト)")
    result = fetcher.fetch(source, target_account_id="liver_manager", mock=True, dry_run=True)
    check("FetchResult returned", isinstance(result, FetchResult))
    check("status OK", result.status == "OK")
    check("items is list", isinstance(result.items, list))
    check("1件以上", len(result.items) >= 1)

    item = result.items[0]
    check("item is RawSourceItem", isinstance(item, RawSourceItem))
    check("item_type=article", item.item_type == "article")
    check("fetch_adapter=article_fetcher", item.fetch_adapter == "article_fetcher")
    check("rights_status=reference_only", item.rights_status == "reference_only")
    check("media_policy=plan_only", item.media_policy == "plan_only")
    check("source_id preserved", item.source_id == source["source_id"])
    check("target_account_id set", item.target_account_id == "liver_manager")

    print("\n[4] dry_run=True + confirm_fetch=False → BLOCKED")
    result2 = fetcher.fetch(
        source,
        target_account_id="liver_manager",
        mock=False,
        dry_run=True,
        confirm_fetch=False,
    )
    check("FetchResult returned", isinstance(result2, FetchResult))
    check("status BLOCKED (confirm_fetch=False)", result2.status == "BLOCKED")

    print("\n[5] mock=False + dry_run=True + confirm_fetch=True → NOT_READY (allow_network_fetch=False)")
    source_no_network = dict(source)
    source_no_network["allow_network_fetch"] = False
    result3 = fetcher.fetch(
        source_no_network,
        target_account_id="liver_manager",
        mock=False,
        dry_run=True,
        confirm_fetch=True,
    )
    check("FetchResult returned", isinstance(result3, FetchResult))
    check("status BLOCKED/NOT_READY when allow_network_fetch=False",
          result3.status in ("BLOCKED", "NOT_READY"))

    print("\n[6] source_platform=article も受け付ける")
    article_source = dict(source)
    article_source["source_platform"] = "article"
    result4 = fetcher.fetch(article_source, target_account_id="liver_manager", mock=True, dry_run=True)
    check("article platform OK", result4.status == "OK")

    print("\n[7] max_items 制限")
    source_small = dict(source)
    source_small["max_items_per_run"] = 1
    result5 = fetcher.fetch(source_small, target_account_id="liver_manager", mock=True, dry_run=True, max_items=1)
    check("max_items=1 respected", len(result5.items) <= 1)

    print("\n--- 結果 ---")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"PASS: {passed} / FAIL: {failed}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
