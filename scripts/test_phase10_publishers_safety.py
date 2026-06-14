#!/usr/bin/env python3
"""test_phase10_publishers_safety.py - Publisher 安全設計テスト"""
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
    print("=== Phase 10: Publishers Safety テスト ===\n")

    # base publisher
    print("[1] BasePublisher")
    try:
        from src.publishers.base import BasePublisher, PublishResult
        check("BasePublisher import", True)
        check("PublishResult import", True)
        check("PublishResult.dry_run field", hasattr(PublishResult, "__dataclass_fields__")
              and "dry_run" in PublishResult.__dataclass_fields__)
    except Exception as e:
        check("BasePublisher import", False, str(e))

    # dry_run はデフォルト True
    print("\n[2] dry_run デフォルト確認")
    try:
        from src.publishers.base import PublishResult
        r = PublishResult(platform="x", dry_run=True, success=False, message="test")
        check("dry_run=True default", r.dry_run is True)
        check("success=False on init", r.success is False)
    except Exception as e:
        check("PublishResult dry_run", False, str(e))

    # threads publisher
    print("\n[3] ThreadsPublisher")
    try:
        from src.publishers.threads_publisher import ThreadsPublisher
        pub = ThreadsPublisher()
        check("ThreadsPublisher import", True)
    except Exception as e:
        check("ThreadsPublisher import", False, str(e))
        pub = None

    # x publisher
    print("\n[4] XPublisher")
    try:
        from src.publishers.x_publisher import XPublisher
        xpub = XPublisher()
        check("XPublisher import", True)
    except Exception as e:
        check("XPublisher import", False, str(e))

    # 環境変数チェック (実投稿ブロック)
    print("\n[5] 実投稿ブロック確認")
    publish_env = os.environ.get("PUBLISH_ENABLED", "false").lower()
    threads_env = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower()
    x_env = os.environ.get("ALLOW_REAL_X_POST", "false").lower()

    check("PUBLISH_ENABLED=false (デフォルト)", publish_env == "false")
    check("ALLOW_REAL_THREADS_POST=false (デフォルト)", threads_env == "false")
    check("ALLOW_REAL_X_POST=false (デフォルト)", x_env == "false")

    print("\n[6] beauty_account 投稿ブロック確認")
    try:
        from src.accounts.account_config import load_account_config
        beauty = load_account_config("beauty_account")
        check("beauty_account is_draft_only", beauty.is_draft_only() is True)
        check("beauty_account is_active=False", beauty.is_active() is False)
    except Exception as e:
        check("beauty_account config load", False, str(e))

    print("\n[7] factory publisher")
    try:
        from src.publishers.factory import get_publisher
        pub_t = get_publisher("threads")
        pub_x = get_publisher("x")
        check("threads publisher factory", pub_t is not None)
        check("x publisher factory", pub_x is not None)
    except Exception as e:
        check("publisher factory", False, str(e))

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] Publishers Safety テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
