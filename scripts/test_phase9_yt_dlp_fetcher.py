#!/usr/bin/env python3
"""test_phase9_yt_dlp_fetcher.py - yt-dlp Fetcher テスト"""
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
    print("=== Phase 9: yt-dlp Fetcher テスト ===\n")

    from src.reference.fetchers.yt_dlp_fetcher import YtDlpFetcher, _platform_from_url

    # プラットフォーム判定
    print("[1] プラットフォーム判定")
    check("youtube URL", _platform_from_url("https://www.youtube.com/watch?v=abc123") == "youtube")
    check("shorts URL", _platform_from_url("https://www.youtube.com/shorts/abc123") == "youtube_shorts")
    check("youtu.be URL", _platform_from_url("https://youtu.be/abc123") == "youtube")
    check("tiktok URL", _platform_from_url("https://www.tiktok.com/@user/video/123") == "tiktok")
    check("unknown URL", _platform_from_url("https://example.com/video") == "unknown")

    # モック取得
    print("\n[2] モック取得テスト")
    fetcher = YtDlpFetcher()
    src = {"source_id": "yt_001", "source_platform": "youtube",
           "source_handle": "@test", "source_url": "https://youtube.com/c/test",
           "rights_policy": "reference_only", "reuse_policy": "reference_only", "media_policy": "do_not_download"}

    result = fetcher.fetch(src, target_account_id="liver_manager", mock=True, max_items=3)
    check("mock status=OK", result.status == "OK")
    check("mock items > 0", len(result.items) > 0)
    check("mock flag", result.mock is True)
    check("item_type=video", all(i.item_type == "video" for i in result.items))
    check("source_platform=youtube", all(i.source_platform == "youtube" for i in result.items))

    # BLOCKED テスト
    print("\n[3] confirm_fetch なし = BLOCKED")
    result_blocked = fetcher.fetch(src, mock=False, confirm_fetch=False)
    check("BLOCKED status", result_blocked.status == "BLOCKED")

    # NOT_INSTALLED テスト (yt-dlp 未インストール想定)
    print("\n[4] yt-dlp 未インストール = NOT_INSTALLED")
    import subprocess
    yt_installed = False
    try:
        r = subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=3)
        yt_installed = r.returncode == 0
    except Exception:
        pass

    if not yt_installed:
        result_ni = fetcher.fetch(src, mock=False, confirm_fetch=True)
        check("NOT_INSTALLED status", result_ni.status == "NOT_INSTALLED")
        print("  [INFO] yt-dlp 未インストール。NOT_INSTALLED として正常。")
    else:
        print("  [INFO] yt-dlp インストール済み。NOT_INSTALLED テストをスキップ。")
        check("yt-dlp installed", True, "インストール済み")

    # source_url なし = NOT_READY
    print("\n[5] source_url なし = NOT_READY")
    src_no_url = dict(src)
    src_no_url["source_url"] = ""
    result_nourl = fetcher.fetch(src_no_url, mock=False, confirm_fetch=True)
    check("source_url なし = NOT_READY or NOT_INSTALLED", result_nourl.status in ("NOT_READY", "NOT_INSTALLED"))

    # アダプター情報
    print("\n[6] アダプター属性確認")
    check("adapter_name", fetcher.adapter_name == "yt_dlp")
    check("supported_platforms", "youtube" in fetcher.supported_platforms)
    check("tiktok in platforms", "tiktok" in fetcher.supported_platforms)

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed:
        sys.exit(1)
    print("[OK] yt-dlp Fetcher テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
