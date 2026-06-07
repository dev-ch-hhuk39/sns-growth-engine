"""
activate_learning_rule.py - 学習ルール有効化（Phase 4.5）

learning_rules の active を false → true に変更する。
または prompt_improvement_suggestions の APPROVED 提案から learning_rules 候補を作成する。

設計原則:
  - --confirm-activate フラグが必須（誤操作防止）
  - active=true の自動設定は絶対禁止
  - forbidden_keywords / forbidden_themes と矛盾するルールは有効化不可
  - night_scout に代理店向けルールを復活させるルールは禁止
  - liver_manager に怪しい副業訴求ルールは禁止
  - activationログを残す
  - prompt/code の自動変更禁止

使い方:
  # 改善提案から learning_rules 候補を作成（active=false）
  python scripts/activate_learning_rule.py --suggestion-id sug-XXXXXXXX --create-rule

  # 実行（dry-run 確認）
  python scripts/activate_learning_rule.py --suggestion-id sug-XXXXXXXX --create-rule

  # learning_rule を active=true にする
  python scripts/activate_learning_rule.py --rule-id rule-XXXXXXXX --confirm-activate

  # Sheets書き込みあり
  python scripts/activate_learning_rule.py --rule-id rule-XXXXXXXX --confirm-activate --use-sheets
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
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

try:
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS, ACCOUNT_FORBIDDEN_THEMES
except ImportError:
    ACCOUNT_FORBIDDEN_KEYWORDS = {}
    ACCOUNT_FORBIDDEN_THEMES = {}

# 禁止ルールパターン（night_scout / liver_manager 固有）
PROHIBITED_RULE_PATTERNS: dict[str, list[str]] = {
    "night_scout": [
        "代理店", "代理店向け", "代理店パートナー", "パートナー募集",
        "代理店を増やす", "スカウト代理店", "組織的に稼ぐ", "情報商材",
    ],
    "liver_manager": [
        "代理店", "情報商材", "誰でも稼げる", "副業で稼ぐ", "怪しい副業",
        "ネットワーク", "MLM",
    ],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def _check_forbidden(text: str, account_id: str | None) -> tuple[bool, str]:
    """ルールテキストが forbidden と矛盾するか確認。"""
    if not account_id:
        return False, ""
    keywords = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
    themes = ACCOUNT_FORBIDDEN_THEMES.get(account_id, [])
    prohibited = PROHIBITED_RULE_PATTERNS.get(account_id, [])

    all_forbidden = set(keywords) | set(themes) | set(prohibited)
    for item in all_forbidden:
        if item in text:
            return True, f"禁止パターン一致: {item!r}"
    return False, ""


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


def _write_activation_log(rule_id: str, account_id: str | None, action: str) -> None:
    """activation ログをローカルファイルに追記する。"""
    log_dir = os.path.join(_V2_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "learning_rule_activations.log")
    entry = f"{_now()} | {action} | rule_id={rule_id} | account_id={account_id or 'unknown'}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"  [LOG] activation log → {log_path}")


def create_rule_from_suggestion(
    sheets,
    suggestion_id: str,
    *,
    dry_run: bool = True,
) -> bool:
    """APPROVED 提案から learning_rules 候補を作成する（active=false）。"""
    suggestion = _find_suggestion(sheets, suggestion_id)
    if suggestion is None:
        print(f"[ERROR] 提案が見つかりません: suggestion_id={suggestion_id!r}")
        return False

    status = str(suggestion.get("status", "")).upper()
    if status != "APPROVED":
        print(f"[ERROR] status={status!r} の提案は learning_rule に変換できません（APPROVED のみ可）")
        return False

    account_id = suggestion.get("account_id", "")

    # 禁止チェック
    text = " ".join([
        str(suggestion.get("suggested_change", "")),
        str(suggestion.get("reason", "")),
        str(suggestion.get("expected_impact", "")),
    ])
    conflict, detail = _check_forbidden(text, account_id)
    if conflict:
        print(f"[FAIL] 禁止パターンと矛盾するため learning_rule に変換できません: {detail}")
        return False

    rule_id = f"rule-{_short_uuid()}"
    rule_row = {
        "rule_id": rule_id,
        "account_id": account_id,
        "created_at": _now(),
        "source_suggestion_id": suggestion_id,
        "insight_type": "prompt_refinement",
        "condition": str(suggestion.get("current_behavior", "")),
        "action": str(suggestion.get("suggested_change", "")),
        "description": str(suggestion.get("reason", "")),
        "priority": str(suggestion.get("priority", "medium")),
        "active": "false",
        "applied_count": "0",
        "notes": f"Created from suggestion {suggestion_id}",
    }

    print(f"\n  提案内容:")
    print(f"    suggestion_id : {suggestion_id}")
    print(f"    account_id    : {account_id}")
    print(f"    type          : {suggestion.get('suggestion_type', '?')}")
    print(f"    change        : {str(suggestion.get('suggested_change', '?'))[:100]}")
    print(f"\n  → learning_rule 候補: rule_id={rule_id} (active=false)")
    print(f"  → active=true にするには: --rule-id {rule_id} --confirm-activate")

    if dry_run:
        print(f"  [dry-run] Sheets書き込みをスキップ（--use-sheets で実行）")
        return True

    if hasattr(sheets, "_sh") and not sheets.dry_run:
        try:
            ws = sheets._sh.worksheet("learning_rules")
            from sheets_client import TAB_DEFINITIONS
            headers = TAB_DEFINITIONS.get("learning_rules", list(rule_row.keys()))
            ws.append_row([rule_row.get(h, "") for h in headers])

            # 提案の status を CONVERTED_TO_RULE に更新
            ws_sug = sheets._sh.worksheet("prompt_improvement_suggestions")
            sug_rows = ws_sug.get_all_records()
            for idx, r in enumerate(sug_rows, 2):
                if r.get("suggestion_id") == suggestion_id:
                    from sheets_client import TAB_DEFINITIONS as TD
                    sug_headers = TD.get("prompt_improvement_suggestions", list(r.keys()))
                    if "status" in sug_headers:
                        status_col = sug_headers.index("status") + 1
                        ws_sug.update_cell(idx, status_col, "CONVERTED_TO_RULE")
                    break
        except Exception as e:
            print(f"[ERROR] Sheets書き込みエラー: {e}")
            return False

    print(f"  [OK] learning_rule 候補を作成しました: rule_id={rule_id} (active=false)")
    _write_activation_log(rule_id, account_id, "RULE_CREATED_FROM_SUGGESTION")
    return True


def activate_rule(
    sheets,
    rule_id: str,
    *,
    dry_run: bool = True,
) -> bool:
    """learning_rule を active=true にする（--confirm-activate 必須）。"""
    row = _find_rule(sheets, rule_id)
    if row is None:
        print(f"[ERROR] ルールが見つかりません: rule_id={rule_id!r}")
        return False

    current_active = str(row.get("active", "false")).lower()
    if current_active == "true":
        print(f"[INFO] すでに active=true です: {rule_id!r}")
        return True

    account_id = row.get("account_id", "")

    # 禁止チェック
    text = " ".join([
        str(row.get("description", "")),
        str(row.get("condition", "")),
        str(row.get("action", "")),
    ])
    conflict, detail = _check_forbidden(text, account_id)
    if conflict:
        print(f"[FAIL] 禁止パターンと矛盾するため active=true にできません: {detail}")
        return False

    print(f"\n  ルール内容:")
    print(f"    rule_id     : {rule_id}")
    print(f"    account_id  : {account_id}")
    print(f"    condition   : {str(row.get('condition', '?'))[:80]}")
    print(f"    action      : {str(row.get('action', '?'))[:80]}")
    print(f"    description : {str(row.get('description', '?'))[:80]}")

    if dry_run:
        print(f"  [dry-run] {rule_id!r} を active=true にする（--confirm-activate で実行）")
        return True

    if hasattr(sheets, "_sh") and not sheets.dry_run:
        try:
            ws = sheets._sh.worksheet("learning_rules")
            rows = ws.get_all_records()
            for idx, r in enumerate(rows, 2):
                if r.get("rule_id") == rule_id:
                    from sheets_client import TAB_DEFINITIONS
                    headers = TAB_DEFINITIONS.get("learning_rules", list(r.keys()))
                    if "active" in headers:
                        active_col = headers.index("active") + 1
                        ws.update_cell(idx, active_col, "true")
                    break
        except Exception as e:
            print(f"[ERROR] Sheets更新エラー: {e}")
            return False

    print(f"  [ACTIVATED] {rule_id!r} を active=true に更新しました")
    _write_activation_log(rule_id, account_id, "RULE_ACTIVATED")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="学習ルール有効化（Phase 4.5）",
        epilog=(
            "例:\n"
            "  python scripts/activate_learning_rule.py --suggestion-id sug-XXXXXXXX --create-rule\n"
            "  python scripts/activate_learning_rule.py --rule-id rule-XXXXXXXX --confirm-activate"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--suggestion-id", help="変換元の提案ID (APPROVED のみ)")
    target_group.add_argument("--rule-id", help="有効化する learning_rule の ID")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--create-rule", action="store_true",
        help="提案から learning_rule 候補を作成（active=false）",
    )
    mode_group.add_argument(
        "--confirm-activate", action="store_true",
        help="active=true に変更（必須フラグ）",
    )

    parser.add_argument("--use-sheets", action="store_true", help="実 Sheets に書き込む")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  activate_learning_rule.py - 学習ルール有効化（Phase 4.5）")
    print("=" * 60)
    print("[INFO] prompt/code の自動変更は行いません。")
    print("[INFO] active=true は --confirm-activate フラグが必須です。")

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
        dry_run_mode = not (args.use_sheets and (args.confirm_activate or args.create_rule))
        sheets = SheetsClient(
            sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"],
            dry_run=dry_run_mode,
        )

    # ---- 処理分岐 ----

    if args.suggestion_id:
        if not args.create_rule:
            print(f"[INFO] dry-run: 提案 {args.suggestion_id!r} から rule 作成を確認します")
            print("[NOTE] 実行するには --create-rule を追加してください")
        ok = create_rule_from_suggestion(
            sheets,
            args.suggestion_id,
            dry_run=not args.create_rule,
        )
    elif args.rule_id:
        if not args.confirm_activate:
            print(f"[INFO] dry-run: rule {args.rule_id!r} の activate を確認します")
            print("[NOTE] 実行するには --confirm-activate を追加してください")
        ok = activate_rule(
            sheets,
            args.rule_id,
            dry_run=not args.confirm_activate,
        )
    else:
        print("[ERROR] --suggestion-id または --rule-id を指定してください")
        sys.exit(1)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
