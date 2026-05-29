"""
setup_and_verify.py - Google Sheets 初期セットアップと検証

機能:
  --dry-run   : 何を作るか表示（書き込みしない）
  --setup     : 12タブ作成 + accounts/categories/templates/rules シード投入
  --verify    : タブ存在・シードデータを検証（読み取りのみ）
  --test-write: logs タブにテスト行を1件書き込む
  --all       : --setup → --verify → --test-write を順に実行

重要:
  --test-write または --all がない限り書き込みしない。
  --dry-run 時は絶対に書き込まない。

使い方:
  # 何をするか確認（書き込みなし）
  python scripts/setup_and_verify.py --dry-run

  # セットアップのみ
  python scripts/setup_and_verify.py --setup

  # セットアップ + 検証
  python scripts/setup_and_verify.py --setup --verify

  # 書き込みテスト
  python scripts/setup_and_verify.py --test-write

  # 全部（セットアップ → 検証 → 書き込みテスト）
  python scripts/setup_and_verify.py --all
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

from config_loader import get_config, get_config_partial
from sheets_client import SheetsClient, MockSheetsClient, make_client, TAB_DEFINITIONS
from seeds import (
    ACCOUNT_SEEDS_V2, CATEGORY_SEEDS,
    PROMPT_TEMPLATE_SEEDS, DISTRIBUTION_RULE_SEEDS,
)


# ------------------------------------------------------------------ #
# セットアップ
# ------------------------------------------------------------------ #

def run_setup(sheets: "SheetsClient | MockSheetsClient") -> None:
    """12タブ作成 + 全シードデータ投入（冪等）。"""
    print("\n[setup] タブ初期化を開始します")
    sheets.setup_all()

    print("\n[setup] content_categories シード投入")
    added = sheets.seed_tab("content_categories", CATEGORY_SEEDS, "category_id")
    print(f"  → {added} 件追加")

    print("\n[setup] prompt_templates シード投入")
    added = sheets.seed_tab("prompt_templates", PROMPT_TEMPLATE_SEEDS, "template_id")
    print(f"  → {added} 件追加")

    print("\n[setup] distribution_rules シード投入")
    added = sheets.seed_tab("distribution_rules", DISTRIBUTION_RULE_SEEDS, "rule_id")
    print(f"  → {added} 件追加")

    print("\n[setup] セットアップ完了")


# ------------------------------------------------------------------ #
# 検証
# ------------------------------------------------------------------ #

def run_verify(sheets: "SheetsClient | MockSheetsClient") -> bool:
    """タブ存在・シードデータを検証する。問題があれば False を返す。"""
    print("\n[verify] 検証を開始します")
    all_ok = True

    # 1. タブ存在確認
    expected = set(TAB_DEFINITIONS.keys())
    expected_count = len(expected)
    try:
        existing = set(sheets.list_tabs())
        missing = expected - existing
        if missing:
            print(f"  [FAIL] 不足タブ: {missing}")
            all_ok = False
        else:
            extra = existing - expected
            note = f" (追加タブ: {extra})" if extra else ""
            print(f"  [PASS] {expected_count}タブすべて存在確認OK{note}")
    except Exception as e:
        print(f"  [FAIL] タブ一覧取得エラー: {e}")
        all_ok = False

    # 2. accounts 確認
    try:
        accounts = sheets.get_active_accounts()
        ids = {a.get("account_id") for a in accounts}
        missing_accts = {"night_scout", "liver_manager"} - ids
        if missing_accts:
            print(f"  [WARN] 未登録アカウント: {missing_accts}  → --setup を実行してください")
            all_ok = False
        else:
            print(f"  [PASS] accounts: night_scout / liver_manager 確認OK ({len(accounts)}件)")
    except Exception as e:
        print(f"  [FAIL] accounts 取得エラー: {e}")
        all_ok = False

    # 3. content_categories 確認
    try:
        cats_ns = sheets.get_active_categories("night_scout")
        cats_lm = sheets.get_active_categories("liver_manager")
        total = len(cats_ns) + len(cats_lm)
        if total == 0:
            print(f"  [WARN] content_categories が空 → --setup を実行してください")
            all_ok = False
        else:
            print(f"  [PASS] content_categories: night_scout={len(cats_ns)}件 liver_manager={len(cats_lm)}件")
    except Exception as e:
        print(f"  [FAIL] content_categories 取得エラー: {e}")
        all_ok = False

    # 4. prompt_templates 確認
    try:
        templates = sheets.get_prompt_templates()
        if not templates:
            print(f"  [WARN] prompt_templates が空 → --setup を実行してください")
            all_ok = False
        else:
            names = [t.get("template_name", "?") for t in templates[:3]]
            print(f"  [PASS] prompt_templates: {len(templates)}件 (例: {names})")
    except Exception as e:
        print(f"  [FAIL] prompt_templates 取得エラー: {e}")
        all_ok = False

    # 5. drafts タブ確認（読み取りのみ）
    try:
        drafts = sheets.get_drafts(limit=3)
        print(f"  [PASS] drafts タブ読み取りOK ({len(drafts)}件)")
    except Exception as e:
        print(f"  [FAIL] drafts タブ読み取りエラー: {e}")
        all_ok = False

    # 6. social_derivatives タブ確認
    try:
        ders = sheets.get_social_derivatives(limit=3)
        print(f"  [PASS] social_derivatives タブ読み取りOK ({len(ders)}件)")
    except Exception as e:
        print(f"  [FAIL] social_derivatives タブ読み取りエラー: {e}")
        all_ok = False

    status = "OK" if all_ok else "WARN/FAIL あり"
    print(f"\n[verify] 検証完了: {status}")
    return all_ok


# ------------------------------------------------------------------ #
# テスト書き込み
# ------------------------------------------------------------------ #

def run_test_write(sheets: "SheetsClient | MockSheetsClient") -> bool:
    """logs タブにテスト行を1件書き込む。"""
    print("\n[test-write] テスト書き込みを開始します")
    try:
        sheets.log(
            operation="setup_and_verify",
            status="OK",
            message="Phase 2.6 setup_and_verify テスト書き込み成功",
            account_id="night_scout",
            details="test-write による接続確認",
        )
        print("  [PASS] logs タブへのテスト書き込み完了")

        # drafts にもテスト行を書き込む
        draft_id = sheets.save_draft(
            account_id="night_scout",
            title="【接続確認】Phase 2.6 setup_and_verify",
            body_md="# 接続確認\nこれは setup_and_verify --test-write による接続確認用データです。",
            status="DRAFT",
            generation_model="test",
            prompt_version="v0",
            post_mode="test",
        )
        print(f"  [PASS] drafts タブへのテスト書き込み完了: draft_id={draft_id}")
        print("\n[test-write] 完了（不要なら Sheets 上でテスト行を削除してください）")
        return True
    except Exception as e:
        print(f"  [FAIL] テスト書き込みエラー: {e}")
        return False


# ------------------------------------------------------------------ #
# dry-run 表示
# ------------------------------------------------------------------ #

def run_dry_run_preview() -> None:
    """--dry-run 時に実施予定の処理を表示する（書き込みしない）。"""
    print("\n[dry-run] 以下の処理を実行予定です（書き込みはしません）:")
    print(f"  --setup  : 12タブを冪等作成 + accounts/categories/templates/rules シード投入")
    expected = list(TAB_DEFINITIONS.keys())
    print(f"    タブ一覧: {expected}")
    print(f"    accounts: {[s['account_id'] for s in ACCOUNT_SEEDS_V2]}")
    print(f"    content_categories: {len(CATEGORY_SEEDS)}件")
    print(f"    prompt_templates: {len(PROMPT_TEMPLATE_SEEDS)}件")
    print(f"    distribution_rules: {len(DISTRIBUTION_RULE_SEEDS)}件")
    print(f"  --verify  : タブ存在・データ検証（読み取りのみ）")
    print(f"  --test-write: logs/drafts タブにテスト行を1件ずつ書き込み")
    print("\n[dry-run] 実際に実行するには --setup / --verify / --test-write / --all を使ってください")


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="Google Sheets 初期セットアップと検証")
    parser.add_argument("--dry-run", action="store_true", help="何をするか表示（書き込みしない）")
    parser.add_argument("--setup", action="store_true", help="タブ作成 + シード投入")
    parser.add_argument("--verify", action="store_true", help="タブ存在・データ検証")
    parser.add_argument("--test-write", action="store_true", help="logs/drafts にテスト行を書き込む")
    parser.add_argument("--all", action="store_true", help="setup → verify → test-write を順に実行")
    args = parser.parse_args()

    # フラグ検証
    if args.dry_run and (args.test_write or args.all):
        print("[ERROR] --dry-run と --test-write / --all は同時に指定できません")
        sys.exit(1)

    if not any([args.dry_run, args.setup, args.verify, args.test_write, args.all]):
        print("[INFO] フラグが未指定です。--dry-run で確認するか、--setup --verify を指定してください")
        parser.print_help()
        sys.exit(0)

    print("=" * 55)
    print("  setup_and_verify.py - Sheets セットアップ & 検証")
    print("=" * 55)

    # --dry-run: 書き込みなし
    if args.dry_run:
        run_dry_run_preview()

        # --verify も一緒に指定された場合は読み取り確認
        if args.verify:
            cfg = get_config_partial()
            if cfg.get("sa_dict") and cfg.get("sheet_id"):
                sheets = make_client(cfg, dry_run=True, force_mock=False)
                run_verify(sheets)
            else:
                print("\n[verify] 認証情報未設定のためスキップします（MockSheetsClient では検証不可）")
        sys.exit(0)

    # --setup / --verify / --test-write / --all はすべて実際の Sheets が必要
    need_write = args.setup or args.test_write or args.all
    try:
        cfg = get_config()
    except ValueError as e:
        if not need_write and args.verify:
            print(f"[WARN] 認証情報未設定のため読み取り検証もスキップします: {e}")
            sys.exit(1)
        print(f"[ERROR] 認証情報が必要です: {e}")
        print("  → .env に SNS_MASTER_SHEET_ID と SA_JSON_BASE64 / GCP_SA_JSON を設定してください")
        sys.exit(1)

    dry_run_for_sheets = not need_write
    sheets = SheetsClient(
        sheet_id=cfg["sheet_id"],
        sa_dict=cfg["sa_dict"],
        dry_run=dry_run_for_sheets,
    )

    ok = True

    # --all: setup → verify → test-write を順に実行
    if args.all:
        print("\n[all] setup → verify → test-write を順に実行します")
        # setup には dry_run=False が必要なので再生成
        sheets_write = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        run_setup(sheets_write)
        ok = run_verify(sheets_write) and ok
        ok = run_test_write(sheets_write) and ok
    else:
        if args.setup:
            sheets_write = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
            run_setup(sheets_write)

        if args.verify:
            # verify は読み取りのみでよい
            sheets_ro = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
            ok = run_verify(sheets_ro) and ok

        if args.test_write:
            sheets_write = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
            ok = run_test_write(sheets_write) and ok

    print("\n" + "=" * 55)
    if ok:
        print("  ✓ 完了: すべての処理が成功しました")
        if args.setup or args.all:
            print("  → 次: python scripts/preflight_check.py で総合診断を確認してください")
    else:
        print("  ✗ 一部処理に問題があります。上記のログを確認してください")
    print("=" * 55)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
