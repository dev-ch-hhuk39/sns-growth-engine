"""シートタブ名を英語から日本語表示名に移行するCLIツール。

Usage:
    python3 scripts/migrate_sheet_tabs_to_japanese.py --dry-run
    python3 scripts/migrate_sheet_tabs_to_japanese.py --confirm-sheets-migration

--dry-run: 変更内容を表示するが実際には変更しない。
--confirm-sheets-migration: 実際にタブ名をリネームする。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()


def _build_client():
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


def run(dry_run: bool) -> None:
    from sheets_client import TAB_DEFINITIONS, TAB_DISPLAY_NAMES

    sheet_id = os.environ.get("SNS_MASTER_SHEET_ID", "").strip()
    if not sheet_id:
        print("ERROR: SNS_MASTER_SHEET_ID が未設定です")
        sys.exit(1)

    gc = _build_client()
    sh = gc.open_by_key(sheet_id)

    existing_titles = {ws.title: ws for ws in sh.worksheets()}

    rename_plan: list[tuple[str, str, str]] = []  # (logical, current_title, new_title)
    skip_already_done: list[str] = []
    skip_not_found: list[str] = []

    for logical_name in TAB_DEFINITIONS:
        display_name = TAB_DISPLAY_NAMES.get(logical_name, logical_name)
        if display_name in existing_titles:
            skip_already_done.append(display_name)
            continue
        if logical_name in existing_titles:
            rename_plan.append((logical_name, logical_name, display_name))
            continue
        skip_not_found.append(logical_name)

    print("=== シートタブ日本語化 移行プラン ===")
    print(f"スプレッドシートID: {sheet_id}")
    print()

    if skip_already_done:
        print(f"[SKIP] 日本語タブ名が既に存在: {len(skip_already_done)} 件")
        for t in skip_already_done:
            print(f"  OK  {t!r}")
        print()

    if rename_plan:
        print(f"[RENAME] リネーム対象: {len(rename_plan)} 件")
        for logical, current, new in rename_plan:
            mark = "[DRY]" if dry_run else "[RENAME]"
            print(f"  {mark}  {current!r}  →  {new!r}")
        print()

    if skip_not_found:
        print(f"[SKIP] スプレッドシートにタブが存在しない（作成は ensure_tabs で行う）: {len(skip_not_found)} 件")
        for t in skip_not_found:
            print(f"  NOT_FOUND  {t!r}")
        print()

    if not rename_plan:
        print("リネームが必要なタブはありません。処理完了。")
        return

    if dry_run:
        print("--dry-run モード: 実際の変更は行いません。")
        print(f"実際に移行するには: --confirm-sheets-migration を使用してください。")
        return

    print(f"実際にリネームします ({len(rename_plan)} 件)...")
    renamed = 0
    for logical, current, new in rename_plan:
        ws = existing_titles[current]
        try:
            ws.update_title(new)
            print(f"  DONE  {current!r}  →  {new!r}")
            renamed += 1
            time.sleep(1.0)  # Sheets API レート制限
        except Exception as e:
            print(f"  ERROR  {current!r}: {e}")

    print()
    print(f"移行完了: {renamed}/{len(rename_plan)} 件リネーム成功")


def main() -> None:
    parser = argparse.ArgumentParser(description="シートタブ名を日本語表示名に移行する")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="変更内容を表示するのみ")
    mode.add_argument(
        "--confirm-sheets-migration",
        action="store_true",
        help="実際にタブ名をリネームする",
    )
    args = parser.parse_args()

    dry_run = args.dry_run
    run(dry_run=dry_run)


if __name__ == "__main__":
    main()
