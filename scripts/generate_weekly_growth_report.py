"""
generate_weekly_growth_report.py - 週次改善レポート生成（Phase 4.4）

Sheets からデータを取得し、アカウント別週次改善レポートを生成する。
MarkdownとJSONの両形式で出力する。

出力先:
  exports/hermes/weekly_growth_report_{account_id}_{date}.md
  exports/hermes/weekly_growth_report_{account_id}_{date}.json

使い方:
  python scripts/generate_weekly_growth_report.py --account-id night_scout
  python scripts/generate_weekly_growth_report.py --account-id night_scout --output-dir exports/hermes
  python scripts/generate_weekly_growth_report.py --all-accounts
  python scripts/generate_weekly_growth_report.py --mock --account-id night_scout

禁止事項:
  - 自動投稿・Sheets書き込み
  - learning_rules の自動 active=true 設定
  - 改善提案の自動反映
"""
from __future__ import annotations

import argparse
import json
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
from learning.weekly_report_builder import build_weekly_report, build_markdown_report

SUPPORTED_ACCOUNTS = ["night_scout", "liver_manager"]


def _safe_get_tab(sheets, tab_name: str, account_id: str | None) -> list[dict]:
    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet(tab_name)
            rows = ws.get_all_records()
            if account_id:
                rows = [r for r in rows if r.get("account_id") == account_id]
            return rows
        except Exception:
            return []
    attr = "_" + tab_name.replace("-", "_")
    rows = getattr(sheets, attr, [])
    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]
    return [dict(r) for r in rows]


def generate_report_for_account(
    sheets,
    account_id: str,
    *,
    output_dir: str = "exports/hermes",
) -> tuple[str, str]:
    """1アカウントのレポートを生成。(md_path, json_path) を返す。"""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    os.makedirs(output_dir, exist_ok=True)

    posted_results = _safe_get_tab(sheets, "posted_results", account_id)
    queue_items = _safe_get_tab(sheets, "queue", account_id)
    learning_rules = _safe_get_tab(sheets, "learning_rules", account_id)
    suggestions = _safe_get_tab(sheets, "prompt_improvement_suggestions", account_id)
    category_scores = _safe_get_tab(sheets, "category_scores", account_id)

    report_data = build_weekly_report(
        account_id,
        posted_results=posted_results,
        queue_items=queue_items,
        learning_rules=learning_rules,
        suggestions=suggestions,
        category_scores=category_scores,
        now=now,
    )

    # Markdown出力
    md_path = os.path.join(output_dir, f"weekly_growth_report_{account_id}_{date_str}.md")
    md_content = build_markdown_report(report_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # JSON出力
    json_path = os.path.join(output_dir, f"weekly_growth_report_{account_id}_{date_str}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    return md_path, json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="週次改善レポート生成")
    acct_group = parser.add_mutually_exclusive_group(required=True)
    acct_group.add_argument("--account-id", help="対象アカウントID (例: night_scout)")
    acct_group.add_argument("--all-accounts", action="store_true", help="全アカウント分を生成")
    parser.add_argument(
        "--output-dir", default="exports/hermes",
        help="出力ディレクトリ（デフォルト: exports/hermes）",
    )
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  generate_weekly_growth_report.py - 週次改善レポート生成（Phase 4.4）")
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

    accounts = SUPPORTED_ACCOUNTS if args.all_accounts else [args.account_id]
    print(f"[INFO] 対象アカウント: {accounts}")
    print(f"[INFO] 出力先: {args.output_dir}/")
    print("[INFO] 自動反映はしません（MarkdownとJSONの出力のみ）")

    for account_id in accounts:
        print(f"\n  アカウント: {account_id}")
        try:
            md_path, json_path = generate_report_for_account(
                sheets, account_id, output_dir=args.output_dir
            )
            print(f"  [OK] Markdown: {md_path}")
            print(f"  [OK] JSON:     {json_path}")
        except Exception as e:
            print(f"  [ERROR] {account_id}: {e}")

    print("\n[完了] 週次改善レポートを生成しました")
    print("[注意] このファイルには機密情報が含まれる場合があります。git commit しないでください。")
    print("[次のステップ] Hermes Agent に渡して提案を生成し、imports/hermes/ に保存してください")
    print("  → python scripts/import_improvement_suggestions.py --from-hermes --use-sheets")


if __name__ == "__main__":
    main()
