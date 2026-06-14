#!/usr/bin/env python3
"""test_phase9_tiktok_to_ytdlp_fetcher.py"""
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
    print("=== Phase 9: TikTok-to-ytdlp Fetcher テスト ===\n")

    from src.reference.fetchers.tiktok_to_ytdlp_fetcher import TiktokToYtdlpFetcher
    fetcher = TiktokToYtdlpFetcher()

    src = {
        "source_id": "tiktok_001",
        "source_platform": "tiktok",
        "source_handle": "@test_tiktok",
        "source_url": "https://www.tiktok.com/@test_user",
        "rights_policy": "reference_only",
        "media_policy": "do_not_download",
    }

    print("[1] アダプター属性")
    check("adapter_name", fetcher.adapter_name == "tiktok_to_ytdlp")
    check("tiktok in supported_platforms", "tiktok" in fetcher.supported_platforms)

    print("\n[2] モック取得")
    result = fetcher.fetch(src, target_account_id="liver_manager", mock=True, max_items=3)
    check("mock status=OK", result.status == "OK")
    check("mock items > 0", len(result.items) > 0)
    check("mock flag", result.mock is True)
    check("source_platform=tiktok", all(i.source_platform == "tiktok" for i in result.items))

    print("\n[3] confirm_fetch なし = BLOCKED")
    result_blocked = fetcher.fetch(src, mock=False, confirm_fetch=False)
    check("BLOCKED", result_blocked.status == "BLOCKED")

    print("\n[4] tiktok-to-ytdlp 未インストール = NOT_INSTALLED")
    import subprocess
    installed = False
    try:
        r = subprocess.run(["tiktok-to-ytdlp", "--help"], capture_output=True, timeout=3)
        installed = r.returncode == 0
    except Exception:
        pass

    if not installed:
        result_ni = fetcher.fetch(src, mock=False, confirm_fetch=True)
        check("NOT_INSTALLED", result_ni.status == "NOT_INSTALLED")
        print("  [INFO] tiktok-to-ytdlp 未インストール。NOT_INSTALLED として正常。")
    else:
        check("installed", True, "インストール済み")

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] TikTok-to-ytdlp Fetcher テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
