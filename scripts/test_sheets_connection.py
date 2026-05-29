"""
test_sheets_connection.py - Google Sheets 実接続確認

認証情報（SA_JSON_BASE64 または GCP_SA_JSON）または SNS_MASTER_SHEET_ID が
未設定の場合は sys.exit(0) でスキップする（CI 友好的）。

使い方:
  # 読み取り確認のみ（書き込まない）
  python scripts/test_sheets_connection.py --dry-run

  # 実際にテスト行を書き込む
  python scripts/test_sheets_connection.py --test-write

安全ガード:
  - --test-write なしの場合は書き込みしない（safe デフォルト）
  - SNS 投稿は一切行わない
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

from config_loader import get_config_partial


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Sheets 実接続確認")
    parser.add_argument("--dry-run", action="store_true", help="読み取り確認のみ（書き込まない）")
    parser.add_argument("--test-write", action="store_true", help="テスト行を書き込む")
    args = parser.parse_args()

    if args.test_write and args.dry_run:
        print("[ERROR] --test-write と --dry-run は同時に指定できません")
        sys.exit(1)

    cfg = get_config_partial()
    if not cfg.get("sa_dict"):
        print("[SKIP] SA_JSON_BASE64 または GCP_SA_JSON が未設定のため test_sheets_connection.py をスキップします")
        sys.exit(0)
    if not cfg.get("sheet_id"):
        print("[SKIP] SNS_MASTER_SHEET_ID が未設定のため test_sheets_connection.py をスキップします")
        sys.exit(0)

    # test-write 指定時のみ実際に書き込む（デフォルトは安全に dry_run=True）
    dry_run = not args.test_write

    from sheets_client import SheetsClient

    print("=" * 60)
    print("Google Sheets 実接続確認")
    print(f"sheet_id={cfg['sheet_id'][:12]}... dry_run={dry_run}")
    print("=" * 60)

    passed = 0
    failed = 0

    try:
        sheets = SheetsClient(
            sheet_id=cfg["sheet_id"],
            sa_dict=cfg["sa_dict"],
            dry_run=dry_run,
        )
        print("[OK] SheetsClient 初期化成功")
    except Exception as e:
        print(f"[FAIL] SheetsClient 初期化失敗: {e}")
        sys.exit(1)

    # ---- Test 1: accounts タブ読み取り ----
    print("\n[Test 1] accounts タブ読み取り")
    try:
        accounts = sheets.get_active_accounts()
        if accounts:
            for a in accounts:
                aid = a.get("account_id", "?")
                name = a.get("account_name", "?")
                print(f"  [OK] account_id={aid} name={name!r}")
            passed += 1
        else:
            print("  [WARN] accounts が空です（setup_sheets.py を実行してください）")
            passed += 1  # 空でも接続成功
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ---- Test 2: content_categories タブ読み取り ----
    print("\n[Test 2] content_categories タブ読み取り")
    try:
        cats_ns = sheets.get_active_categories("night_scout")
        cats_lm = sheets.get_active_categories("liver_manager")
        print(f"  [OK] night_scout: {len(cats_ns)} 件 / liver_manager: {len(cats_lm)} 件")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ---- Test 3: drafts タブ読み取り ----
    print("\n[Test 3] drafts タブ読み取り")
    try:
        drafts = sheets.get_drafts(limit=3)
        print(f"  [OK] drafts: {len(drafts)} 件（最大3件取得）")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ---- Test 4: social_derivatives タブ読み取り ----
    print("\n[Test 4] social_derivatives タブ読み取り")
    try:
        ders = sheets.get_social_derivatives(limit=3)
        print(f"  [OK] social_derivatives: {len(ders)} 件（最大3件取得）")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ---- Test 5: queue タブ読み取り ----
    print("\n[Test 5] queue タブ読み取り")
    try:
        result = sheets.find_queue_item("__nonexistent__", "x")
        print(f"  [OK] find_queue_item: {result}")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ---- Test 6: テスト書き込み（--test-write 時のみ） ----
    if args.test_write:
        print("\n[Test 6] テスト書き込み（drafts タブ）")
        try:
            draft_id = sheets.save_draft(
                account_id="night_scout",
                title="【接続確認テスト】Phase 2.5",
                body_md="# テスト\nこれはPhase 2.5の接続確認テストです。不要なら削除してください。",
                status="DRAFT",
                generation_model="test",
                prompt_version="v0",
                post_mode="test",
            )
            print(f"  [OK] save_draft: draft_id={draft_id}")
            sheets.log(
                "test_sheets_connection", "OK",
                "Phase 2.5 接続確認テスト書き込み完了",
                account_id="night_scout",
                details=f"draft_id={draft_id}",
            )
            print("  [OK] log 書き込み完了")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] テスト書き込み失敗: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Google Sheets 実接続確認 完了: {passed} PASS / {failed} FAIL")
    if not args.test_write:
        print("  ※ 読み取り確認のみ実行（書き込みなし）")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
