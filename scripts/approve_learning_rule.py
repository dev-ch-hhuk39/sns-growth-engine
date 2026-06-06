"""
approve_learning_rule.py - 学習ルール / 改善提案承認（Phase 4.1）

prompt_improvement_suggestions タブの提案、または learning_rules タブのルールを
人間が明示的に承認するスクリプト。

設計原則:
  - --confirm-approve フラグが必須（誤操作防止）
  - active=true の自動設定は絶対禁止（このスクリプト経由のみ）
  - 承認後も Sheets への実書き込みは --use-sheets が必要

使い方:
  # 改善提案の承認
  python scripts/approve_learning_rule.py --suggestion-id sug-XXXXXXXX --confirm-approve

  # learning_rule の active=true 設定
  python scripts/approve_learning_rule.py --rule-id rule-XXXXXXXX --confirm-approve

  # dry-run 確認
  python scripts/approve_learning_rule.py --suggestion-id sug-XXXXXXXX
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_config
from sheets_client import MockSheetsClient, SheetsClient


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_suggestion(sheets, suggestion_id: str) -> dict | None:
    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet("prompt_improvement_suggestions")
            rows = ws.get_all_records()
            for r in rows:
                if r.get("suggestion_id") == suggestion_id:
                    return r
        except Exception:
            pass
    else:
        rows = getattr(sheets, "_prompt_improvement_suggestions", [])
        for r in rows:
            if r.get("suggestion_id") == suggestion_id:
                return dict(r)
    return None


def _find_rule(sheets, rule_id: str) -> dict | None:
    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet("learning_rules")
            rows = ws.get_all_records()
            for r in rows:
                if r.get("rule_id") == rule_id:
                    return r
        except Exception:
            pass
    else:
        rows = getattr(sheets, "_learning_rules", [])
        for r in rows:
            if r.get("rule_id") == rule_id:
                return dict(r)
    return None


def approve_suggestion(
    sheets,
    suggestion_id: str,
    *,
    dry_run: bool = True,
) -> bool:
    """提案を APPROVED に変更する。"""
    row = _find_suggestion(sheets, suggestion_id)
    if row is None:
        print(f"[ERROR] 提案が見つかりません: suggestion_id={suggestion_id!r}")
        return False

    current_status = str(row.get("status", "")).upper()
    if current_status == "APPROVED":
        print(f"[INFO] すでに APPROVED です: {suggestion_id!r}")
        return True
    if current_status == "REJECTED":
        print(f"[WARN] REJECTED 済みの提案です。承認するには手動で status を変更してください: {suggestion_id!r}")
        return False

    print(f"  提案内容:")
    print(f"    type    : {row.get('suggestion_type', '?')}")
    print(f"    priority: {row.get('priority', '?')}")
    print(f"    change  : {str(row.get('suggested_change', '?'))[:100]}")

    if dry_run:
        print(f"  [dry-run] {suggestion_id!r} を APPROVED にする（--confirm-approve で実行）")
        return True

    if hasattr(sheets, "_sh") and not sheets.dry_run:
        try:
            ws = sheets._sh.worksheet("prompt_improvement_suggestions")
            rows = ws.get_all_records()
            for idx, r in enumerate(rows, 2):
                if r.get("suggestion_id") == suggestion_id:
                    from sheets_client import TAB_DEFINITIONS
                    headers = TAB_DEFINITIONS.get("prompt_improvement_suggestions", list(r.keys()))
                    status_col = headers.index("status") + 1 if "status" in headers else None
                    reviewed_by_col = headers.index("reviewed_by") + 1 if "reviewed_by" in headers else None
                    reviewed_at_col = headers.index("reviewed_at") + 1 if "reviewed_at" in headers else None
                    if status_col:
                        ws.update_cell(idx, status_col, "APPROVED")
                    if reviewed_by_col:
                        ws.update_cell(idx, reviewed_by_col, "human")
                    if reviewed_at_col:
                        ws.update_cell(idx, reviewed_at_col, _now())
                    break
        except Exception as e:
            print(f"[ERROR] Sheets更新エラー: {e}")
            return False

    print(f"  [APPROVED] {suggestion_id!r} を APPROVED に更新しました（reviewed_by=human）")
    return True


def approve_rule(
    sheets,
    rule_id: str,
    *,
    dry_run: bool = True,
) -> bool:
    """learning_rule を active=true にする。"""
    row = _find_rule(sheets, rule_id)
    if row is None:
        print(f"[ERROR] ルールが見つかりません: rule_id={rule_id!r}")
        return False

    current_active = str(row.get("active", "false")).lower()
    if current_active == "true":
        print(f"[INFO] すでに active=true です: {rule_id!r}")
        return True

    print(f"  ルール内容:")
    print(f"    type   : {row.get('insight_type', '?')}")
    print(f"    content: {str(row.get('content', '?'))[:100]}")

    if dry_run:
        print(f"  [dry-run] {rule_id!r} を active=true にする（--confirm-approve で実行）")
        return True

    if hasattr(sheets, "_sh") and not sheets.dry_run:
        try:
            ws = sheets._sh.worksheet("learning_rules")
            rows = ws.get_all_records()
            from sheets_client import TAB_DEFINITIONS
            headers = TAB_DEFINITIONS.get("learning_rules", [])
            for idx, r in enumerate(rows, 2):
                if r.get("rule_id") == rule_id:
                    active_col = headers.index("active") + 1 if "active" in headers else None
                    if active_col:
                        ws.update_cell(idx, active_col, "true")
                    break
        except Exception as e:
            print(f"[ERROR] Sheets更新エラー: {e}")
            return False

    print(f"  [ACTIVATED] {rule_id!r} を active=true に更新しました")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="学習ルール / 改善提案承認")
    parser.add_argument("--suggestion-id", help="承認する提案の suggestion_id")
    parser.add_argument("--rule-id", help="有効化する learning_rule の rule_id")
    parser.add_argument(
        "--confirm-approve", action="store_true",
        help="承認を実際に実行（省略時は dry-run）",
    )
    parser.add_argument("--use-sheets", action="store_true", help="実 Sheets に接続")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    if not args.suggestion_id and not args.rule_id:
        print("[ERROR] --suggestion-id または --rule-id を指定してください")
        sys.exit(1)

    print("=" * 60)
    print("  approve_learning_rule.py - 学習ルール / 改善提案承認")
    print("=" * 60)

    if not args.confirm_approve:
        print("[INFO] --confirm-approve 未指定: dry-run モード（実際の変更なし）")

    if args.mock or not args.use_sheets:
        if not args.use_sheets:
            print("[INFO] --use-sheets 未指定: MockSheetsClient を使用")
        sheets = MockSheetsClient(dry_run=True)
    else:
        try:
            cfg = get_config()
        except ValueError as e:
            print(f"[ERROR] 認証情報が必要です: {e}")
            sys.exit(1)
        sheets = SheetsClient(
            sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"],
            dry_run=not args.confirm_approve,
        )

    dry_run = not args.confirm_approve
    success = True

    if args.suggestion_id:
        print(f"\n[改善提案の承認] suggestion_id={args.suggestion_id!r}")
        success = approve_suggestion(sheets, args.suggestion_id, dry_run=dry_run)

    if args.rule_id:
        print(f"\n[学習ルール有効化] rule_id={args.rule_id!r}")
        success = approve_rule(sheets, args.rule_id, dry_run=dry_run) and success

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
