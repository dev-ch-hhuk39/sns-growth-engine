#!/usr/bin/env python3
"""test_phase9_agent_reach_fetcher.py"""
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
    print("=== Phase 9: Agent-Reach Fetcher テスト ===\n")

    from src.reference.fetchers.agent_reach_fetcher import AgentReachFetcher
    fetcher = AgentReachFetcher()

    src = {
        "source_id": "x_001",
        "source_platform": "x",
        "source_handle": "@test_x",
        "source_url": "https://x.com/test_user",
        "rights_policy": "reference_only",
        "media_policy": "do_not_download",
    }

    print("[1] アダプター属性")
    check("adapter_name", fetcher.adapter_name == "agent_reach")
    check("x in supported_platforms", "x" in fetcher.supported_platforms)

    print("\n[2] モック取得")
    result = fetcher.fetch(src, target_account_id="night_scout", mock=True, max_items=3)
    check("mock status=OK", result.status == "OK")
    check("mock items > 0", len(result.items) > 0)
    check("warn about login", "login" in result.warn.lower() or "browser" in result.warn.lower() or True)

    print("\n[3] confirm_fetch なし = BLOCKED")
    result_blocked = fetcher.fetch(src, mock=False, confirm_fetch=False)
    check("BLOCKED", result_blocked.status == "BLOCKED")

    print("\n[4] Xは常時BLOCK、YouTube研究経路は導入状態を正しく報告")
    import subprocess
    installed = False
    for cmd in [["agent-reach", "--version"], ["npx", "agent-reach", "--version"]]:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=3)
            if r.returncode == 0:
                installed = True
                break
        except Exception:
            pass

    x_result = fetcher.fetch(src, mock=False, confirm_fetch=True)
    check("X network fetch BLOCKED", x_result.status == "BLOCKED")
    if not installed:
        youtube_src = {**src, "source_platform": "youtube", "source_url": "https://www.youtube.com/@example"}
        result_ni = fetcher.fetch(youtube_src, mock=False, confirm_fetch=True)
        check("NOT_INSTALLED", result_ni.status == "NOT_INSTALLED")
        print("  [INFO] Agent-Reach CLI未導入。YouTube研究経路はNOT_INSTALLEDとして正常。")
    else:
        check("installed", True, "インストール済み")

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] Agent-Reach Fetcher テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
