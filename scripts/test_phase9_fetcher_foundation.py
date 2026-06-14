#!/usr/bin/env python3
"""test_phase9_fetcher_foundation.py - Phase 9 Fetcher基盤テスト"""
from __future__ import annotations
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
results = []


def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    icon = "✓" if condition else "✗"
    print(f"  {icon} [{status}] {name}" + (f": {detail}" if detail else ""))
    return condition


def main():
    print("=== Phase 9: Fetcher Foundation テスト ===\n")

    # 1. BaseFetcher import
    print("[1] BaseFetcher インポートテスト")
    try:
        from src.reference.fetchers.base_fetcher import BaseFetcher, FetchResult, RawSourceItem
        check("BaseFetcher import", True)
        check("RawSourceItem dataclass", "raw_item_id" in RawSourceItem.__dataclass_fields__)
        check("FetchResult dataclass", "status" in FetchResult.__dataclass_fields__)
    except Exception as e:
        check("BaseFetcher import", False, str(e))

    # 2. RawSourceItem
    print("\n[2] RawSourceItem テスト")
    try:
        from src.reference.fetchers.base_fetcher import RawSourceItem
        item = RawSourceItem(
            source_id="src_001",
            source_platform="youtube",
            text="テスト投稿",
            like_count=1000,
        )
        check("RawSourceItem 生成", item.raw_item_id != "")
        check("RawSourceItem like_count", item.like_count == 1000)
        d = item.to_dict()
        check("to_dict() 動作", isinstance(d, dict))
        check("to_dict() raw_item_id", "raw_item_id" in d)
        check("to_dict() buzz_score", "buzz_score" in d)

        item2 = RawSourceItem.from_dict(d)
        check("from_dict() 往復", item2.source_id == "src_001")
    except Exception as e:
        check("RawSourceItem テスト", False, str(e))

    # 3. FetcherRegistry
    print("\n[3] FetcherRegistry テスト")
    try:
        from src.reference.fetchers.fetcher_registry import FetcherRegistry, get_fetcher
        reg = FetcherRegistry()
        check("FetcherRegistry 生成", True)

        fetcher = get_fetcher("manual_json", "x")
        check("manual_json fetcher", fetcher is not None)
        check("fetcher.adapter_name", fetcher.adapter_name == "json_import")

        fetcher_yt = get_fetcher("yt_dlp", "youtube")
        check("yt_dlp fetcher", fetcher_yt.adapter_name == "yt_dlp")

        adapters = reg.list_adapters()
        check("list_adapters() 動作", len(adapters) >= 5)
    except Exception as e:
        check("FetcherRegistry テスト", False, str(e))

    # 4. JsonImportFetcher mock
    print("\n[4] JsonImportFetcher モックテスト")
    try:
        from src.reference.fetchers.json_import_fetcher import JsonImportFetcher
        fetcher = JsonImportFetcher()
        source = {
            "source_id": "test_src_001",
            "source_platform": "x",
            "source_handle": "@test_handle",
            "source_url": "https://x.com/test",
            "collection_method": "manual_json",
            "rights_policy": "reference_only",
            "reuse_policy": "reference_only",
            "media_policy": "do_not_download",
        }
        result = fetcher.fetch(source, target_account_id="night_scout", mock=True)
        check("JsonImportFetcher mock status=OK", result.status == "OK")
        check("JsonImportFetcher mock items > 0", len(result.items) > 0)
        check("JsonImportFetcher mock=True flag", result.mock is True)
    except Exception as e:
        check("JsonImportFetcher テスト", False, str(e))

    # 5. confirm_fetch なし = BLOCKED
    print("\n[5] confirm_fetch なし → BLOCKED テスト")
    try:
        from src.reference.fetchers.yt_dlp_fetcher import YtDlpFetcher
        fetcher = YtDlpFetcher()
        source = {"source_id": "yt_001", "source_platform": "youtube", "source_url": "https://youtube.com"}
        result = fetcher.fetch(source, mock=False, confirm_fetch=False)
        check("yt_dlp fetch なし BLOCKED", result.status == "BLOCKED")
    except Exception as e:
        check("BLOCKED テスト", False, str(e))

    # 6. scrape_disallowed → BLOCKED
    print("\n[6] scrape_disallowed → BLOCKED テスト")
    try:
        from src.reference.fetchers.fetcher_registry import get_fetcher
        fetcher = get_fetcher("scrape_disallowed", "x")
        source = {"source_id": "block_001", "source_platform": "x", "collection_method": "scrape_disallowed"}
        result = fetcher.fetch(source, mock=False)
        check("scrape_disallowed BLOCKED", result.status == "BLOCKED")
    except Exception as e:
        check("scrape_disallowed テスト", False, str(e))

    # 7. __init__ export
    print("\n[7] fetchers package __init__ テスト")
    try:
        from src.reference.fetchers import BaseFetcher, FetchResult, RawSourceItem, FetcherRegistry, get_fetcher
        check("fetchers package import", True)
    except Exception as e:
        check("fetchers package import", False, str(e))

    # 結果
    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = sum(1 for _, s, _ in results if s == FAIL)
    print(f"結果: {passed} PASS / {failed} FAIL / {len(results)} total")

    if failed > 0:
        print("\n[FAIL 一覧]")
        for name, status, detail in results:
            if status == FAIL:
                print(f"  ✗ {name}: {detail}")
        sys.exit(1)

    print("\n[OK] Phase 9 Fetcher Foundation テスト完了")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
