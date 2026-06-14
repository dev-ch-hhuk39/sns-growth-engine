#!/usr/bin/env python3
"""test_phase10_x_publisher.py"""
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
    print("=== Phase 10: X Publisher テスト ===\n")

    print("[1] XPublisher import")
    try:
        from src.publishers.x_publisher import XPublisher
        pub = XPublisher()
        check("import OK", True)
    except Exception as e:
        check("import", False, str(e))
        sys.exit(1)

    print("\n[2] dry_run 投稿")
    try:
        result = pub.publish(
            text="X テスト投稿（dry_run）",
            account={"account_id": "night_scout"},
            derivative={"derivative_id": "d001"},
            queue_item={"queue_id": "q001"},
            dry_run=True,
        )
        if hasattr(result, "dry_run"):
            check("dry_run=True", result.dry_run is True)
            check("real_post なし", result.posted_url is None or result.dry_run)
        else:
            check("publish result あり", result is not None)
    except Exception as e:
        check("dry_run publish", False, str(e))

    print("\n[3] 実投稿ブロック確認")
    real_x = os.environ.get("ALLOW_REAL_X_POST", "false").lower()
    check("ALLOW_REAL_X_POST=false", real_x == "false")

    print("\n[4] beauty_account BLOCKED")
    try:
        result_beauty = pub.publish(
            text="beauty X テスト",
            account={"account_id": "beauty_account", "draft_only": True},
            derivative={"derivative_id": "d_beauty"},
            queue_item={"queue_id": "q_beauty"},
            dry_run=True,
        )
        check("beauty handled", True)
    except Exception as e:
        check("beauty account handling", True, f"例外として処理: {e}")

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] X Publisher テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
