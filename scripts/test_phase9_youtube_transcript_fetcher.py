#!/usr/bin/env python3
"""test_phase9_youtube_transcript_fetcher.py"""
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
    print("=== Phase 9: YouTube Transcript Fetcher テスト ===\n")

    from src.reference.fetchers.youtube_transcript_fetcher import (
        YoutubeTranscriptFetcher, _extract_video_id
    )
    fetcher = YoutubeTranscriptFetcher()

    print("[1] video_id 抽出テスト")
    check("watch URL", _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ")
    check("shorts URL", _extract_video_id("https://www.youtube.com/shorts/abc12345678") == "abc12345678")
    check("youtu.be URL", _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ")
    check("invalid URL", _extract_video_id("https://example.com/") == "")

    src = {
        "source_id": "yt_001",
        "source_platform": "youtube",
        "source_url": "https://youtube.com/watch?v=mock",
        "rights_policy": "reference_only",
        "media_policy": "do_not_download",
    }

    print("\n[2] モック取得")
    result = fetcher.fetch(src, target_account_id="liver_manager", mock=True)
    check("mock status=OK", result.status == "OK")
    check("items > 0", len(result.items) > 0)
    check("transcript あり", all(i.transcript is not None for i in result.items))

    print("\n[3] confirm_fetch なし = BLOCKED")
    result_blocked = fetcher.fetch(src, mock=False, confirm_fetch=False)
    check("BLOCKED", result_blocked.status == "BLOCKED")

    print("\n[4] youtube-transcript-api 未インストール = NOT_INSTALLED")
    try:
        import youtube_transcript_api
        print("  [INFO] youtube-transcript-api インストール済み")
        check("installed", True)
    except ImportError:
        result_ni = fetcher.fetch(src, mock=False, confirm_fetch=True)
        check("NOT_INSTALLED", result_ni.status in ("NOT_INSTALLED", "NOT_READY_TRANSCRIPT"))
        print("  [INFO] 未インストール。NOT_INSTALLED として正常。")

    print("\n[5] アダプター属性")
    check("adapter_name", fetcher.adapter_name == "youtube_transcript")
    check("youtube in platforms", "youtube" in fetcher.supported_platforms)

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] YouTube Transcript Fetcher テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
