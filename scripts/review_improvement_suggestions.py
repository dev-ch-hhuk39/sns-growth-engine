"""
review_improvement_suggestions.py - 改善提案レビュー表示（Phase 4.0）

prompt_improvement_suggestions タブの WAITING_REVIEW 提案を一覧表示する。
このスクリプトは読み取り専用。承認は approve_learning_rule.py で実施する。

使い方:
  python scripts/review_improvement_suggestions.py --account-id night_scout
  python scripts/review_improvement_suggestions.py --mock
  python scripts/review_improvement_suggestions.py --show-all
"""
from __future__ import annotations

import argparse
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_config
from sheets_client import MockSheetsClient, SheetsClient


def _get_suggestions(sheets, account_id: str | None, *, show_all: bool = False) -> list[dict]:
    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet("prompt_improvement_suggestions")
            rows = ws.get_all_records()
            if account_id:
                rows = [r for r in rows if r.get("account_id") == account_id]
        except Exception:
            rows = []
    else:
        rows = getattr(sheets, "_prompt_improvement_suggestions", [])
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        rows = [dict(r) for r in rows]

    if show_all:
        return rows
    return [r for r in rows if str(r.get("status", "")).upper() == "WAITING_REVIEW"]


def display_suggestions(suggestions: list[dict], *, show_all: bool = False) -> None:
    label = "全提案" if show_all else "WAITING_REVIEW の提案"
    print(f"\n{label}: {len(suggestions)}件")
    if not suggestions:
        print("  (なし)")
        return

    for i, s in enumerate(suggestions, 1):
        print(f"\n  [{i}] suggestion_id: {s.get('suggestion_id', '?')}")
        print(f"       account_id    : {s.get('account_id', '?')}")
        print(f"       status        : {s.get('status', '?')}")
        print(f"       priority      : {s.get('priority', '?')}")
        print(f"       source        : {s.get('source', '?')}")
        print(f"       type          : {s.get('suggestion_type', '?')}")
        print(f"       current       : {s.get('current_behavior', '?')[:80]}")
        print(f"       suggested     : {s.get('suggested_change', '?')[:80]}")
        print(f"       reason        : {s.get('reason', '?')[:80]}")
        print(f"       expected      : {s.get('expected_impact', '?')[:60]}")
        print(f"       created_at    : {s.get('created_at', '?')}")
        if s.get("reviewed_at"):
            print(f"       reviewed_at   : {s.get('reviewed_at', '?')}")
            print(f"       reviewed_by   : {s.get('reviewed_by', '?')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="改善提案レビュー表示")
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--show-all", action="store_true", help="全ステータスを表示（デフォルトは WAITING_REVIEW のみ）")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  review_improvement_suggestions.py - 改善提案レビュー")
    print("=" * 60)
    print("[INFO] このスクリプトは読み取り専用です。承認は approve_learning_rule.py で実施してください。")

    if args.mock:
        print("[INFO] MockSheetsClient を使用します")
        sheets = MockSheetsClient(dry_run=True)
    else:
        try:
            cfg = get_config()
        except ValueError as e:
            print(f"[ERROR] 認証情報が必要です: {e}")
            print("  → --mock でモック動作確認できます")
            sys.exit(1)
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)

    suggestions = _get_suggestions(sheets, args.account_id, show_all=args.show_all)
    display_suggestions(suggestions, show_all=args.show_all)

    waiting = sum(1 for s in suggestions if str(s.get("status", "")).upper() == "WAITING_REVIEW")
    print(f"\n[INFO] WAITING_REVIEW: {waiting}件")
    if waiting > 0:
        print("[次のステップ] python scripts/approve_learning_rule.py --suggestion-id <ID> --confirm-approve")


if __name__ == "__main__":
    main()
