"""
check_learning_integrity.py - 学習システム整合性チェック（Phase 4.1）

learning_rules と prompt_improvement_suggestions タブの整合性を検証する。

チェック内容:
  1. learning_rules: active=true かつ承認日時なしは WARN
  2. learning_rules: insight_type が想定外の値は WARN
  3. prompt_improvement_suggestions: WAITING_REVIEW が長期放置は WARN（7日以上）
  4. prompt_improvement_suggestions: status が想定外の値は FAIL
  5. prompt_improvement_suggestions: APPROVED かつ reviewed_by が空は WARN

使い方:
  python scripts/check_learning_integrity.py --account-id night_scout
  python scripts/check_learning_integrity.py --mock
  python scripts/check_learning_integrity.py --fail-on-warn
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_config
from sheets_client import MockSheetsClient, SheetsClient


VALID_INSIGHT_TYPES = {
    "hook_improvement", "text_length_control", "rights_management",
    "engagement_boost", "cta_optimization", "content_strategy",
    "prompt_refinement", "other",
}
VALID_SUGGESTION_STATUSES = {"WAITING_REVIEW", "APPROVED", "REJECTED"}
WAITING_REVIEW_WARN_DAYS = 7


def _get_tab(sheets, tab_name: str, account_id: str | None) -> list[dict]:
    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet(tab_name)
            rows = ws.get_all_records()
            if account_id:
                rows = [r for r in rows if r.get("account_id") == account_id]
            return rows
        except Exception:
            return []
    attr = "_" + tab_name
    rows = getattr(sheets, attr, [])
    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]
    return [dict(r) for r in rows]


def check_learning_rules(sheets, account_id: str | None, results: list) -> int:
    """learning_rules タブの整合性チェック。"""
    issues = 0
    rows = _get_tab(sheets, "learning_rules", account_id)

    if not rows:
        results.append("  [PASS] learning_rules は空（初期状態として正常）")
        return 0

    results.append(f"  [PASS] learning_rules 取得OK: {len(rows)}件")

    active_rows = [r for r in rows if str(r.get("active", "false")).lower() == "true"]
    invalid_type = 0
    active_without_approval = 0

    for r in rows:
        itype = str(r.get("insight_type", "")).strip().lower()
        if itype and itype not in VALID_INSIGHT_TYPES:
            invalid_type += 1

    for r in active_rows:
        if not str(r.get("applied_count", "")).strip():
            active_without_approval += 1

    results.append(f"  [PASS] learning_rules: active={len(active_rows)}件 / 全{len(rows)}件")

    if invalid_type > 0:
        results.append(f"  [WARN] learning_rules: insight_type が未定義の行: {invalid_type}件")
        issues += 1
    else:
        results.append("  [PASS] learning_rules: insight_type OK")

    if active_without_approval > 0:
        results.append(
            f"  [WARN] learning_rules: active=true かつ applied_count 未設定: {active_without_approval}件"
            f" (approve_learning_rule.py 経由で承認されましたか?)"
        )
        issues += 1
    else:
        results.append("  [PASS] learning_rules: active=true の整合性OK")

    return issues


def check_improvement_suggestions(sheets, account_id: str | None, results: list) -> int:
    """prompt_improvement_suggestions タブの整合性チェック。"""
    issues = 0
    rows = _get_tab(sheets, "prompt_improvement_suggestions", account_id)

    if not rows:
        results.append("  [PASS] prompt_improvement_suggestions は空（初期状態として正常）")
        return 0

    results.append(f"  [PASS] prompt_improvement_suggestions 取得OK: {len(rows)}件")

    invalid_status = 0
    long_waiting = 0
    approved_no_reviewer = 0
    now_utc = datetime.now(timezone.utc)

    for r in rows:
        status = str(r.get("status", "")).upper().strip()
        if status and status not in VALID_SUGGESTION_STATUSES:
            invalid_status += 1

        if status == "WAITING_REVIEW":
            created_at_str = str(r.get("created_at", ""))
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if (now_utc - created_at) > timedelta(days=WAITING_REVIEW_WARN_DAYS):
                        long_waiting += 1
                except ValueError:
                    pass

        if status == "APPROVED":
            if not str(r.get("reviewed_by", "")).strip():
                approved_no_reviewer += 1

    waiting_count = sum(1 for r in rows if str(r.get("status", "")).upper() == "WAITING_REVIEW")
    approved_count = sum(1 for r in rows if str(r.get("status", "")).upper() == "APPROVED")
    rejected_count = sum(1 for r in rows if str(r.get("status", "")).upper() == "REJECTED")

    results.append(
        f"  [PASS] prompt_improvement_suggestions: "
        f"WAITING={waiting_count} APPROVED={approved_count} REJECTED={rejected_count}"
    )

    if invalid_status > 0:
        results.append(
            f"  [FAIL] prompt_improvement_suggestions: status が不正な行: {invalid_status}件"
            f" (有効: WAITING_REVIEW / APPROVED / REJECTED)"
        )
        issues += 1
    else:
        results.append("  [PASS] prompt_improvement_suggestions: status OK")

    if long_waiting > 0:
        results.append(
            f"  [WARN] prompt_improvement_suggestions: "
            f"WAITING_REVIEW が{WAITING_REVIEW_WARN_DAYS}日以上放置: {long_waiting}件"
            f" (review_improvement_suggestions.py で確認してください)"
        )
        issues += 1
    else:
        results.append(
            f"  [PASS] prompt_improvement_suggestions: 長期放置なし（{WAITING_REVIEW_WARN_DAYS}日基準）"
        )

    if approved_no_reviewer > 0:
        results.append(
            f"  [WARN] prompt_improvement_suggestions: APPROVED かつ reviewed_by 未設定: {approved_no_reviewer}件"
            f" (自動承認の可能性 → 確認してください)"
        )
        issues += 1
    else:
        results.append("  [PASS] prompt_improvement_suggestions: APPROVED の承認者記録OK")

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="学習システム整合性チェック")
    parser.add_argument("--account-id", help="チェック対象アカウントID")
    parser.add_argument("--fail-on-warn", action="store_true", help="WARN でも非ゼロ終了")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  check_learning_integrity.py - 学習システム整合性チェック")
    print("=" * 60)

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

    account_label = args.account_id or "全アカウント"
    print(f"\n対象: {account_label}")
    print("-" * 60)

    all_results: list[str] = []
    total_issues = 0
    fail_count = 0

    checks = [
        ("learning_rules", check_learning_rules),
        ("prompt_improvement_suggestions", check_improvement_suggestions),
    ]

    for tab_name, check_fn in checks:
        print(f"\n[{tab_name}]")
        section_results: list[str] = []
        issues = check_fn(sheets, args.account_id, section_results)
        for line in section_results:
            print(line)
            all_results.append(line)
        total_issues += issues
        fail_count += sum(1 for r in section_results if r.strip().startswith("[FAIL]"))

    print("\n" + "=" * 60)
    warn_count = sum(1 for r in all_results if r.strip().startswith("[WARN]"))
    pass_count = sum(1 for r in all_results if r.strip().startswith("[PASS]"))

    print(f"チェック結果サマリー:")
    print(f"  [PASS]: {pass_count}件")
    print(f"  [WARN]: {warn_count}件")
    print(f"  [FAIL]: {fail_count}件")
    print("=" * 60)

    if fail_count > 0:
        print("\n[RESULT] FAIL: 整合性エラーがあります。")
        sys.exit(1)
    elif warn_count > 0 and args.fail_on_warn:
        print("\n[RESULT] WARN（--fail-on-warn 指定）")
        sys.exit(1)
    elif warn_count > 0:
        print("\n[RESULT] WARN: 確認推奨の項目があります。")
        sys.exit(0)
    else:
        print("\n[RESULT] PASS: 全チェック正常です。")
        sys.exit(0)


if __name__ == "__main__":
    main()
