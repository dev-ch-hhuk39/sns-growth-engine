#!/usr/bin/env python3
"""test_phase9_browser_export_import.py"""
from __future__ import annotations
import json, os, sys, tempfile
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))

def main():
    print("=== Phase 9: Browser Export / Import テスト ===\n")

    from src.reference.fetchers.browser_export_fetcher import BrowserExportFetcher
    from src.reference.fetchers.json_import_fetcher import JsonImportFetcher

    src = {
        "source_id": "threads_001",
        "source_platform": "threads",
        "source_handle": "@test_threads",
        "source_url": "https://threads.net/@test",
        "rights_policy": "reference_only",
        "media_policy": "do_not_download",
    }

    # BrowserExportFetcher mock
    print("[1] BrowserExportFetcher モック")
    fetcher = BrowserExportFetcher()
    result = fetcher.fetch(src, target_account_id="night_scout", mock=True)
    check("mock status=OK", result.status == "OK")
    check("items > 0", len(result.items) > 0)
    check("adapter_name=browser_export", fetcher.adapter_name == "browser_export")

    # JSON インポートテスト
    print("\n[2] JsonImportFetcher JSON インポート")
    json_fetcher = JsonImportFetcher()

    sample_data = [
        {"post_id": f"p{i:03d}", "text": f"テスト投稿 #{i+1}", "likes": (i+1)*100,
         "views": (i+1)*1000, "url": f"https://x.com/post/{i}"}
        for i in range(5)
    ]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(sample_data, f, ensure_ascii=False)
        tmp_json = f.name

    try:
        result_json = json_fetcher.fetch(
            src, target_account_id="night_scout", mock=False,
            confirm_fetch=True, import_path=tmp_json, max_items=5,
        )
        check("JSON import status=OK", result_json.status == "OK")
        check("JSON import 5件", len(result_json.items) == 5)
        check("post_id 正規化", result_json.items[0].post_id == "p000")
        check("like_count 正規化", result_json.items[0].like_count == 100)
    finally:
        os.unlink(tmp_json)

    # CSV インポートテスト
    print("\n[3] JsonImportFetcher CSV インポート")
    import csv, io
    csv_data = "post_id,text,likes,views\n" + "\n".join(
        f"c{i:03d},CSVテスト#{i+1},{(i+1)*50},{(i+1)*500}" for i in range(3)
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as f:
        f.write(csv_data)
        tmp_csv = f.name

    try:
        result_csv = json_fetcher.fetch(
            src, target_account_id="night_scout", mock=False,
            confirm_fetch=True, import_path=tmp_csv, max_items=3,
        )
        check("CSV import status=OK", result_csv.status == "OK")
        check("CSV import 3件", len(result_csv.items) == 3)
    finally:
        os.unlink(tmp_csv)

    # Markdown インポートテスト
    print("\n[4] BrowserExportFetcher Markdown インポート")
    md_content = "# 参考投稿まとめ\n\n## 投稿1\n内容1の本文です\n\n## 投稿2\n内容2の本文です\n"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(md_content)
        tmp_md = f.name

    try:
        result_md = fetcher.fetch(
            src, target_account_id="night_scout", mock=False,
            confirm_fetch=True, import_path=tmp_md, max_items=5,
        )
        check("Markdown import status=OK or WARN", result_md.status in ("OK", "WARN"))
        check("Markdown items > 0", len(result_md.items) >= 1)
    finally:
        os.unlink(tmp_md)

    # import_path なし = NOT_READY
    print("\n[5] import_path なし = NOT_READY")
    result_nopath = fetcher.fetch(src, mock=False)
    check("NOT_READY", result_nopath.status == "NOT_READY")

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] Browser Export / Import テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
