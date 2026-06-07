"""
review_improvement_suggestions.py - 改善提案レビュー表示（Phase 4.2）

prompt_improvement_suggestions タブの提案を一覧表示する。
このスクリプトは読み取り専用。承認は approve_learning_rule.py で実施する。

使い方:
  python scripts/review_improvement_suggestions.py --account-id night_scout
  python scripts/review_improvement_suggestions.py --mock
  python scripts/review_improvement_suggestions.py --show-all
  python scripts/review_improvement_suggestions.py --status WAITING_REVIEW
  python scripts/review_improvement_suggestions.py --risk-level high
  python scripts/review_improvement_suggestions.py --suggestion-type prompt_change
  python scripts/review_improvement_suggestions.py --account-id night_scout --status APPROVED --risk-level high
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

try:
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS, ACCOUNT_FORBIDDEN_THEMES
except ImportError:
    ACCOUNT_FORBIDDEN_KEYWORDS = {}
    ACCOUNT_FORBIDDEN_THEMES = {}


# Phase 4.2 で整理した有効ステータス一覧
VALID_STATUSES = {
    "WAITING_REVIEW",    # レビュー待ち（デフォルト）
    "APPROVED",          # 承認済み（learning_rules候補化済み）
    "REJECTED",          # 棄却
    "IMPORTED",          # Sheetsへのインポート完了
    "CONVERTED_TO_RULE", # learning_rulesに変換済み
}

VALID_RISK_LEVELS = {"high", "medium", "low", "unknown"}
VALID_SUGGESTION_TYPES = {"prompt_change", "rule_addition", "strategy_change"}


def _has_forbidden_conflict(suggestion: dict, account_id: str | None) -> tuple[bool, str]:
    """提案が forbidden_keywords / forbidden_themes と矛盾するか確認。"""
    if not account_id:
        return False, ""

    keywords = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
    themes = ACCOUNT_FORBIDDEN_THEMES.get(account_id, [])

    text_fields = [
        str(suggestion.get("suggested_change", "")),
        str(suggestion.get("current_behavior", "")),
        str(suggestion.get("reason", "")),
        str(suggestion.get("expected_impact", "")),
    ]
    combined = " ".join(text_fields)

    for kw in keywords:
        if kw in combined:
            return True, f"forbidden_keyword 一致: {kw!r}"
    for theme in themes:
        if theme in combined:
            return True, f"forbidden_theme 一致: {theme!r}"
    return False, ""


def _get_suggestions(
    sheets,
    account_id: str | None,
    *,
    show_all: bool = False,
    status_filter: str | None = None,
    risk_level_filter: str | None = None,
    suggestion_type_filter: str | None = None,
) -> list[dict]:
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

    # ステータスフィルタ
    if status_filter:
        rows = [r for r in rows if str(r.get("status", "")).upper() == status_filter.upper()]
    elif not show_all:
        rows = [r for r in rows if str(r.get("status", "")).upper() == "WAITING_REVIEW"]

    # risk_level フィルタ
    if risk_level_filter:
        rows = [r for r in rows if str(r.get("risk_level", "unknown")).lower() == risk_level_filter.lower()]

    # suggestion_type フィルタ
    if suggestion_type_filter:
        rows = [r for r in rows if str(r.get("suggestion_type", "")).lower() == suggestion_type_filter.lower()]

    return rows


def _risk_label(risk: str) -> str:
    mapping = {"high": "[!HIGH]", "medium": "[MED]", "low": "[low]"}
    return mapping.get(str(risk).lower(), "[?]")


def display_suggestions(
    suggestions: list[dict],
    *,
    show_all: bool = False,
    account_id: str | None = None,
    status_filter: str | None = None,
) -> None:
    if status_filter:
        label = f"status={status_filter} の提案"
    elif show_all:
        label = "全提案"
    else:
        label = "WAITING_REVIEW の提案"

    print(f"\n{label}: {len(suggestions)}件")
    if not suggestions:
        print("  (なし)")
        return

    forbidden_warn_ids: list[str] = []

    for i, s in enumerate(suggestions, 1):
        conflict, conflict_detail = _has_forbidden_conflict(s, account_id)
        risk = str(s.get("risk_level", "unknown")).lower()
        risk_tag = _risk_label(risk)

        print(f"\n  [{i}] {risk_tag} suggestion_id: {s.get('suggestion_id', '?')}")
        print(f"       account_id    : {s.get('account_id', '?')}")
        print(f"       status        : {s.get('status', '?')}")
        print(f"       risk_level    : {risk}")
        print(f"       priority      : {s.get('priority', '?')}")
        print(f"       source        : {s.get('source', '?')}")
        print(f"       type          : {s.get('suggestion_type', '?')}")
        print(f"       current       : {str(s.get('current_behavior', '?'))[:80]}")
        print(f"       suggested     : {str(s.get('suggested_change', '?'))[:80]}")
        print(f"       reason        : {str(s.get('reason', '?'))[:80]}")
        print(f"       expected      : {str(s.get('expected_impact', '?'))[:60]}")
        print(f"       created_at    : {s.get('created_at', '?')}")
        if s.get("reviewed_at"):
            print(f"       reviewed_at   : {s.get('reviewed_at', '?')}")
            print(f"       reviewed_by   : {s.get('reviewed_by', '?')}")
        if conflict:
            print(f"       [WARN REJECT候補] forbidden 矛盾: {conflict_detail}")
            forbidden_warn_ids.append(str(s.get("suggestion_id", "?")))

    if forbidden_warn_ids:
        print(f"\n  [WARN] forbidden矛盾のため REJECT 推奨: {len(forbidden_warn_ids)}件")
        for sid in forbidden_warn_ids:
            print(f"    → python scripts/approve_learning_rule.py --suggestion-id {sid} --reject --confirm-approve")


def _print_status_summary(suggestions: list[dict]) -> None:
    from collections import Counter
    counts = Counter(str(s.get("status", "?")).upper() for s in suggestions)
    print(f"\nステータス内訳:")
    for st in ["WAITING_REVIEW", "APPROVED", "REJECTED", "IMPORTED", "CONVERTED_TO_RULE"]:
        n = counts.get(st, 0)
        if n:
            print(f"  {st}: {n}件")


def main() -> None:
    parser = argparse.ArgumentParser(description="改善提案レビュー表示")
    parser.add_argument("--account-id", help="対象アカウントID（省略時は全アカウント）")
    parser.add_argument("--show-all", action="store_true", help="全ステータスを表示")
    parser.add_argument(
        "--status",
        choices=list(VALID_STATUSES) + [s.lower() for s in VALID_STATUSES],
        help="ステータスでフィルタ（例: WAITING_REVIEW）",
    )
    parser.add_argument(
        "--risk-level",
        choices=list(VALID_RISK_LEVELS),
        dest="risk_level",
        help="risk_level でフィルタ（high/medium/low/unknown）",
    )
    parser.add_argument(
        "--suggestion-type",
        choices=list(VALID_SUGGESTION_TYPES),
        dest="suggestion_type",
        help="suggestion_type でフィルタ（prompt_change/rule_addition/strategy_change）",
    )
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

    # フィルタオプションの表示
    filters_active = []
    if args.account_id:
        filters_active.append(f"account_id={args.account_id}")
    if args.status:
        filters_active.append(f"status={args.status.upper()}")
    if args.risk_level:
        filters_active.append(f"risk_level={args.risk_level}")
    if args.suggestion_type:
        filters_active.append(f"suggestion_type={args.suggestion_type}")
    if filters_active:
        print(f"[FILTER] {' / '.join(filters_active)}")

    # 取得
    all_rows = _get_suggestions(
        sheets,
        args.account_id,
        show_all=True,
    )
    suggestions = _get_suggestions(
        sheets,
        args.account_id,
        show_all=args.show_all,
        status_filter=args.status,
        risk_level_filter=args.risk_level,
        suggestion_type_filter=args.suggestion_type,
    )

    if args.show_all or args.status:
        _print_status_summary(all_rows)

    display_suggestions(
        suggestions,
        show_all=args.show_all,
        account_id=args.account_id,
        status_filter=args.status.upper() if args.status else None,
    )

    waiting = sum(1 for s in all_rows if str(s.get("status", "")).upper() == "WAITING_REVIEW")
    print(f"\n[INFO] 全体 WAITING_REVIEW: {waiting}件")
    if waiting > 0:
        print("[次のステップ] python scripts/approve_learning_rule.py --suggestion-id <ID> --confirm-approve")
    print("[INFO] learning_rules への変換: python scripts/activate_learning_rule.py --suggestion-id <ID> --confirm-activate")


if __name__ == "__main__":
    main()
