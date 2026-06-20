"""SNSマスターシートの初期化 CLI。

新規スプレッドシートに対して TAB_DEFINITIONS の全タブを作成し、
TAB_DISPLAY_NAMES の日本語名でタブを初期化する。

Usage:
    python3 scripts/setup_sheets.py --use-japanese-tabs --dry-run
    python3 scripts/setup_sheets.py --use-japanese-tabs --confirm-setup

--use-japanese-tabs: TAB_DISPLAY_NAMES の日本語タブ名を使用する（推奨）
--dry-run: 作成内容を表示するが実際には作成しない
--confirm-setup: 実際にタブを作成する（SNS_MASTER_SHEET_ID が必要）
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()


def _build_gspread_client():
    import base64
    import json
    import tempfile

    import gspread
    from google.oauth2.service_account import Credentials

    sa_b64 = os.environ.get("SA_JSON_BASE64", "").strip()
    sa_json = os.environ.get("GCP_SA_JSON", "").strip()

    if sa_b64:
        sa_bytes = base64.b64decode(sa_b64)
        sa_dict = json.loads(sa_bytes)
    elif sa_json:
        sa_dict = json.loads(sa_json)
    else:
        raise RuntimeError("SA_JSON_BASE64 または GCP_SA_JSON が未設定です")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sa_dict, f)
        sa_file = f.name

    try:
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(sa_file, scopes=scopes)
        return gspread.authorize(creds)
    finally:
        os.unlink(sa_file)


def run_dry(use_japanese: bool) -> None:
    from sheets_client import TAB_DEFINITIONS, TAB_DISPLAY_NAMES

    sheet_id = os.environ.get("SNS_MASTER_SHEET_ID", "").strip()
    print("=== Sheets セットアップ dry-run ===")
    print(f"SNS_MASTER_SHEET_ID: {'SET' if sheet_id else 'MISSING (dry-runのため続行)'}")
    print(f"日本語タブ名モード: {'ON' if use_japanese else 'OFF'}")
    print()
    print(f"作成予定タブ一覧 ({len(TAB_DEFINITIONS)} 件):")

    for i, (logical_name, headers) in enumerate(TAB_DEFINITIONS.items(), 1):
        display = TAB_DISPLAY_NAMES.get(logical_name, logical_name) if use_japanese else logical_name
        print(f"  {i:2d}. [{logical_name}] → タブ名: '{display}'  (列数: {len(headers)})")

    print()
    print("[DRY_RUN] 実際の作成は行いません。")
    print("実際に作成するには: --confirm-setup を使用してください。")


def run_setup(use_japanese: bool) -> None:
    from sheets_client import TAB_DEFINITIONS, TAB_DISPLAY_NAMES

    sheet_id = os.environ.get("SNS_MASTER_SHEET_ID", "").strip()
    if not sheet_id:
        print("ERROR: SNS_MASTER_SHEET_ID が未設定です")
        print("  .env に SNS_MASTER_SHEET_ID=<スプレッドシートID> を設定してください")
        sys.exit(1)

    sa_ok = bool(os.environ.get("SA_JSON_BASE64") or os.environ.get("GCP_SA_JSON"))
    if not sa_ok:
        print("ERROR: SA_JSON_BASE64 または GCP_SA_JSON が未設定です")
        sys.exit(1)

    print("=== Sheets セットアップ ===")
    print(f"スプレッドシートID: {sheet_id}")
    print(f"日本語タブ名モード: {'ON' if use_japanese else 'OFF'}")
    print()

    gc = _build_gspread_client()
    sh = gc.open_by_key(sheet_id)
    existing = {ws.title for ws in sh.worksheets()}
    print(f"既存タブ数: {len(existing)}")

    created = skipped = 0
    for logical_name, headers in TAB_DEFINITIONS.items():
        display = TAB_DISPLAY_NAMES.get(logical_name, logical_name) if use_japanese else logical_name
        # 既存チェック: 表示名または論理名で存在確認
        if display in existing or logical_name in existing:
            print(f"  [skip] '{display}' は既に存在します")
            skipped += 1
            continue
        try:
            ws = sh.add_worksheet(title=display, rows=1000, cols=len(headers) + 10)
            ws.update([headers], "A1")
            print(f"  [create] '{display}'  ({len(headers)} 列)")
            created += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"  [ERROR] '{display}': {e}")

    print()
    print(f"完了: 作成 {created} / スキップ {skipped} / 合計 {len(TAB_DEFINITIONS)} タブ")
    if created > 0:
        print()
        print("次のステップ:")
        print("  python3 scripts/migrate_sheet_tabs_to_japanese.py --dry-run")


def main() -> None:
    parser = argparse.ArgumentParser(description="SNSマスターシートのタブを初期化する")
    parser.add_argument(
        "--use-japanese-tabs",
        action="store_true",
        help="TAB_DISPLAY_NAMES の日本語タブ名を使用する（推奨）",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="作成内容を表示するのみ")
    mode.add_argument("--confirm-setup", action="store_true", help="実際にタブを作成する")
    args = parser.parse_args()

    if args.dry_run:
        run_dry(use_japanese=args.use_japanese_tabs)
    else:
        run_setup(use_japanese=args.use_japanese_tabs)


if __name__ == "__main__":
    main()
