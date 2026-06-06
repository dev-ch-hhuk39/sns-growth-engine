"""
import_improvement_suggestions.py - 改善提案インポート（Phase 4.0）

Hermes Agent / 外部ファイルからの改善提案を Sheets にインポートする。
全提案は status=WAITING_REVIEW で保存される（active=true 自動設定は禁止）。

使い方:
  # 内容確認のみ（Sheets書き込みなし）
  python scripts/import_improvement_suggestions.py --input FILE.json

  # Sheets に test-write
  python scripts/import_improvement_suggestions.py --input FILE.json --use-sheets --test-write

  # 実際にインポート
  python scripts/import_improvement_suggestions.py --input FILE.json --use-sheets

禁止事項:
  - active=true の自動設定（approve_learning_rule.py 経由のみ）
  - status=APPROVED の自動設定
  - SNS本番投稿
"""
from __future__ import annotations

import argparse
import json
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


REQUIRED_FIELDS = [
    "source", "suggestion_type", "current_behavior", "suggested_change",
    "reason", "expected_impact", "priority",
]

VALID_SOURCES = {"hermes", "manual", "performance_analyzer"}
VALID_TYPES = {"prompt_change", "rule_addition", "strategy_change"}
VALID_PRIORITIES = {"high", "medium", "low"}


def validate_suggestion(raw: dict) -> tuple[bool, str]:
    """提案の検証。(is_valid, error_message) を返す。"""
    missing = [f for f in REQUIRED_FIELDS if not str(raw.get(f, "")).strip()]
    if missing:
        return False, f"必須フィールドが空: {missing}"

    src = str(raw.get("source", "")).lower()
    if src not in VALID_SOURCES:
        return False, f"source が不正: {src!r} (有効: {VALID_SOURCES})"

    stype = str(raw.get("suggestion_type", "")).lower()
    if stype not in VALID_TYPES:
        return False, f"suggestion_type が不正: {stype!r} (有効: {VALID_TYPES})"

    pri = str(raw.get("priority", "")).lower()
    if pri not in VALID_PRIORITIES:
        return False, f"priority が不正: {pri!r} (有効: {VALID_PRIORITIES})"

    # APPROVED / REJECTED の自動設定禁止
    status = str(raw.get("status", "")).upper()
    if status in ("APPROVED", "REJECTED"):
        return False, f"インポート時に status={status} は設定禁止（WAITING_REVIEW のみ）"

    return True, ""


def import_suggestions(
    suggestions_raw: list[dict],
    *,
    sheets,
    account_id: str | None,
    dry_run: bool = True,
    test_write: bool = False,
) -> dict:
    """提案リストをバリデーションして Sheets に保存する。"""
    results = {"imported": 0, "skipped": 0, "errors": []}

    for i, raw in enumerate(suggestions_raw):
        is_valid, err_msg = validate_suggestion(raw)
        if not is_valid:
            print(f"  [SKIP] #{i+1}: {err_msg}")
            results["skipped"] += 1
            results["errors"].append({"index": i, "error": err_msg, "raw": raw})
            continue

        row = {
            "suggestion_id": raw.get("suggestion_id") or f"sug-{_short_uuid()}",
            "account_id": raw.get("account_id") or account_id or "unknown",
            "created_at": raw.get("created_at") or _now(),
            "source": str(raw["source"]).lower(),
            "suggestion_type": str(raw["suggestion_type"]).lower(),
            "target_template": raw.get("target_template", ""),
            "current_behavior": str(raw["current_behavior"]),
            "suggested_change": str(raw["suggested_change"]),
            "reason": str(raw["reason"]),
            "expected_impact": str(raw["expected_impact"]),
            "priority": str(raw["priority"]).lower(),
            "status": "WAITING_REVIEW",
            "reviewed_by": "",
            "reviewed_at": "",
            "notes": raw.get("notes", ""),
        }

        if dry_run and not test_write:
            print(
                f"  [dry-run] #{i+1}: suggestion_id={row['suggestion_id']!r} "
                f"type={row['suggestion_type']!r} priority={row['priority']!r}"
            )
        else:
            if hasattr(sheets, "_sh") and not sheets.dry_run:
                try:
                    ws = sheets._sh.worksheet("prompt_improvement_suggestions")
                    from sheets_client import TAB_DEFINITIONS
                    headers = TAB_DEFINITIONS.get("prompt_improvement_suggestions", list(row.keys()))
                    ws.append_row([row.get(h, "") for h in headers])
                except Exception as e:
                    print(f"  [ERROR] #{i+1}: Sheets書き込みエラー: {e}")
                    results["errors"].append({"index": i, "error": str(e)})
                    results["skipped"] += 1
                    continue
            print(
                f"  [OK] #{i+1}: suggestion_id={row['suggestion_id']!r} "
                f"type={row['suggestion_type']!r} priority={row['priority']!r} → WAITING_REVIEW"
            )

        results["imported"] += 1

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="改善提案インポート")
    parser.add_argument("--input", required=True, help="入力 JSON ファイルパス")
    parser.add_argument("--account-id", help="インポート対象アカウントID")
    parser.add_argument("--use-sheets", action="store_true", help="実 Sheets に接続")
    parser.add_argument("--test-write", action="store_true", help="test-write モード（Sheets書き込みなし）")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  import_improvement_suggestions.py - 改善提案インポート")
    print("=" * 60)

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        print(f"[ERROR] 入力ファイルが見つかりません: {input_path}")
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    # suggestions キーがある場合はそこから取得
    if isinstance(data, dict):
        suggestions_raw = data.get("suggestions", data.get("items", [data]))
    elif isinstance(data, list):
        suggestions_raw = data
    else:
        print("[ERROR] JSON形式が不正です（list または {suggestions: [...]} が必要）")
        sys.exit(1)

    print(f"[INFO] 提案件数: {len(suggestions_raw)}件")
    print(f"[INFO] アカウント: {args.account_id or '（提案内のaccount_idを使用）'}")

    if args.mock or not args.use_sheets:
        if not args.use_sheets:
            print("[INFO] --use-sheets 未指定: dry-run モード（Sheets接続なし）")
        sheets = MockSheetsClient(dry_run=True)
        dry_run = True
    else:
        try:
            cfg = get_config()
        except ValueError as e:
            print(f"[ERROR] 認証情報が必要です: {e}")
            sys.exit(1)
        write_mode = not args.test_write
        sheets = SheetsClient(
            sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"],
            dry_run=not write_mode,
        )
        dry_run = args.test_write

    if args.test_write:
        print("[INFO] --test-write: Sheets に書き込まず検証のみ実行")

    results = import_suggestions(
        suggestions_raw,
        sheets=sheets,
        account_id=args.account_id,
        dry_run=dry_run,
        test_write=args.test_write,
    )

    print(f"\n[SUMMARY] imported={results['imported']} skipped={results['skipped']}")
    if results["errors"]:
        print(f"[WARN] エラー詳細:")
        for e in results["errors"]:
            print(f"  #{e['index']+1}: {e['error']}")
    print("[注意] 全提案は status=WAITING_REVIEW で保存されます。承認は approve_learning_rule.py で実施してください。")


if __name__ == "__main__":
    main()
