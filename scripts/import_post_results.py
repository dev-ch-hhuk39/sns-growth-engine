"""
import_post_results.py - 投稿結果インポート（Phase 5.4）

JSON または CSV から posted_results 相当データを取り込む。
手動入力データや外部エクスポートデータの取り込みに使用。

デフォルトはdry-run（Sheetsへの書き込みなし）。
--use-sheets --test-write で Sheets へのテスト書き込み可能。

禁止事項:
  - X API / Threads API からの直接取得
  - 本番投稿結果の保存（本番APIなし）
  - queue.status=POSTED への変更
  - シークレット値の表示

使い方:
  python scripts/import_post_results.py --input tests/fixtures/sample_post_results_import.json --dry-run
  python scripts/import_post_results.py --input tests/fixtures/sample_post_results_import.csv --dry-run
  python scripts/import_post_results.py --input tests/fixtures/sample_post_results_import.json --use-sheets --test-write
"""
from __future__ import annotations

import argparse
import csv
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

REQUIRED_FIELDS = ["account_id", "platform", "posted_at"]
METRIC_FIELDS = [
    "impressions", "likes", "reposts", "replies",
    "profile_clicks", "line_clicks", "url_clicks",
]


# ------------------------------------------------------------------ #
# パーサー
# ------------------------------------------------------------------ #

def parse_json(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    raise ValueError(f"不正なJSONフォーマット: {path}")


def parse_csv(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def load_input(path: str) -> list[dict]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return parse_json(path)
    elif ext == ".csv":
        return parse_csv(path)
    else:
        raise ValueError(f"サポートされていない形式: {ext}（.json / .csv のみ）")


# ------------------------------------------------------------------ #
# バリデーション
# ------------------------------------------------------------------ #

def validate_records(records: list[dict]) -> tuple[list[dict], list[str]]:
    valid = []
    errors = []
    for i, rec in enumerate(records):
        missing = [f for f in REQUIRED_FIELDS if not rec.get(f)]
        if missing:
            errors.append(f"行{i+1}: 必須フィールド不足 {missing}")
            continue

        # posted_at の検証
        try:
            posted_at = str(rec.get("posted_at", ""))
            if not posted_at:
                raise ValueError("empty")
        except Exception:
            errors.append(f"行{i+1}: posted_at が不正")
            continue

        # セキュリティ: api_key / token 系フィールドは除去
        safe_rec = {k: v for k, v in rec.items()
                    if not any(x in k.lower() for x in ("secret", "token", "key", "password"))}
        valid.append(safe_rec)

    return valid, errors


# ------------------------------------------------------------------ #
# Sheets書き込み
# ------------------------------------------------------------------ #

def write_to_sheets(records: list[dict], test_write: bool) -> None:
    """Sheetsへのテスト書き込み（--test-writeフラグ必須）。"""
    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()
    sheets = SheetsClient(
        sheet_id=cfg["sheet_id"],
        sa_dict=cfg["sa_dict"],
        dry_run=not test_write,
    )

    print(f"  [Sheets] {'test-write' if test_write else 'dry-run'} モード")
    print(f"  [Sheets] {len(records)} 件を処理")

    if test_write:
        # posted_results タブへのテスト書き込み
        # 実際の投稿結果ではなく、fixture由来のテストデータ
        try:
            for rec in records[:3]:  # テストは3件まで
                rec_with_meta = {
                    **rec,
                    "import_source": "test_fixture",
                    "import_at": datetime.now(timezone.utc).isoformat(),
                    "is_test_data": "true",
                }
                sheets.append_row("posted_results", list(rec_with_meta.values()))
            print(f"  [OK] test-write完了（posted_resultsに is_test_data=true で追記）")
        except Exception as e:
            print(f"  [WARN] Sheets書き込みエラー（dry-runにフォールバック）: {e}")
    else:
        print("  [dry-run] Sheets書き込みをスキップ")


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="投稿結果インポート（Phase 5.4）")
    parser.add_argument("--input", required=True, help="入力ファイル（.json / .csv）")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="dry-run（デフォルト: true）")
    parser.add_argument("--use-sheets", action="store_true",
                        help="Sheets クライアントを使用")
    parser.add_argument("--test-write", action="store_true",
                        help="Sheets へのテスト書き込み（--use-sheets と組み合わせて使用）")
    args = parser.parse_args()

    print("=" * 60)
    print("  import_post_results.py - 投稿結果インポート（Phase 5.4）")
    print("=" * 60)
    print(f"[INFO] 入力: {args.input}")
    print(f"[INFO] dry-run={args.dry_run} use-sheets={args.use_sheets} test-write={args.test_write}")
    print("[INFO] 実API / 実投稿 / X API呼び出しは行いません")

    # 入力ファイル読み込み
    if not os.path.isfile(args.input):
        print(f"[FAIL] ファイルが存在しません: {args.input}")
        sys.exit(1)

    try:
        records = load_input(args.input)
    except Exception as e:
        print(f"[FAIL] ファイル読み込みエラー: {e}")
        sys.exit(1)

    print(f"\n[INFO] {len(records)} 件読み込み完了")

    # バリデーション
    valid, errors = validate_records(records)
    if errors:
        print(f"\n[WARN] バリデーションエラー: {len(errors)} 件")
        for err in errors[:5]:
            print(f"  {err}")
        if len(errors) > 5:
            print(f"  ... 他 {len(errors)-5} 件")

    print(f"\n[INFO] 有効レコード: {len(valid)} 件 / 入力: {len(records)} 件")

    # 統計表示
    if valid:
        accounts = {r.get("account_id") for r in valid}
        platforms = {r.get("platform") for r in valid}
        print(f"  accounts: {accounts}")
        print(f"  platforms: {platforms}")

    # Sheets書き込み
    if args.use_sheets:
        if args.test_write:
            print(f"\n[INFO] test-write モードで Sheets へ書き込みます（is_test_data=true）")
            write_to_sheets(valid, test_write=True)
        else:
            print(f"\n[INFO] --test-write なしのため Sheets 書き込みをスキップ")
            write_to_sheets(valid, test_write=False)
    else:
        print(f"\n[dry-run] Sheets書き込みをスキップ（--use-sheets 未指定）")

    print("\n[完了]")
    print("[次のステップ] python scripts/analyze_post_results.py --account-id <id>")


if __name__ == "__main__":
    main()
