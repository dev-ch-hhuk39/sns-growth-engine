"""
run_pipeline.py - Phase 2.5 完全パイプライン CLI

動作モード:
  Mode A (full mock):           --dry-run --mock-llm [--mock-sheets]
  Mode B (Gemini実 + 書き込みなし): --dry-run
  Mode C (Gemini実 + Sheets読):    --dry-run --use-sheets
  Mode D (full real + test write): --use-sheets --test-write

使い方:
  # Mode A: 認証情報なしで全モック確認
  python scripts/run_pipeline.py --account-id night_scout --platforms x,threads --limit 2 --dry-run --mock-llm

  # Mode B: Gemini実API + Sheets書き込みなし
  python scripts/run_pipeline.py --account-id night_scout --dry-run

  # Mode C: Gemini実API + Sheets実読み取り（書き込みなし）
  python scripts/run_pipeline.py --account-id night_scout --dry-run --use-sheets

  # Mode D: 実API + Sheets実書き込み（本番投稿はしない）
  python scripts/run_pipeline.py --account-id night_scout --use-sheets --test-write

安全ガード:
  - PUBLISH_ENABLED=false の間は SNS 投稿処理を実行しない
  - --test-write は Sheets テスト書き込みのみ（SNS には投稿しない）
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

from config_loader import get_config, get_config_partial
from sheets_client import make_client
from draft_generator import generate_drafts
from social_derivative_generator import generate_social_derivatives
from queue_builder import build_queue


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 Phase 2.5 パイプライン")
    parser.add_argument("--account-id", help="対象アカウントID（省略時は全アカウント）")
    parser.add_argument("--platforms", default="x,threads", help="対象プラットフォーム（カンマ区切り）")
    parser.add_argument("--limit", type=int, default=5, help="生成件数上限")
    parser.add_argument("--dry-run", action="store_true", help="スプレッドシートへの書き込みをスキップ")
    parser.add_argument("--mock-llm", action="store_true", help="Gemini API 呼び出しをモック化")
    parser.add_argument("--mock-sheets", action="store_true", help="Sheets を MockSheetsClient に強制切替")
    parser.add_argument("--use-sheets", action="store_true", help="実際のSheetsClientを使用（認証情報必須）")
    parser.add_argument("--test-write", action="store_true", help="Sheetsテスト書き込みを行う（--use-sheetsが必要）")
    args = parser.parse_args()

    # フラグ互換性チェック
    if args.test_write and args.dry_run:
        print("[ERROR] --test-write と --dry-run は同時に指定できません")
        sys.exit(1)
    if args.test_write and not args.use_sheets:
        print("[ERROR] --test-write には --use-sheets が必要です")
        sys.exit(1)
    if args.mock_sheets and args.use_sheets:
        print("[ERROR] --mock-sheets と --use-sheets は同時に指定できません")
        sys.exit(1)

    # 環境変数に反映（他モジュールが参照するため）
    if args.mock_llm:
        os.environ["MOCK_LLM"] = "true"
    if args.mock_sheets:
        os.environ["MOCK_SHEETS"] = "true"

    # dry_run 決定（--test-write が指定された場合のみ書き込み許可）
    if args.test_write:
        dry_run = False
    else:
        dry_run = args.dry_run or os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")

    # モード表示
    mode = _detect_mode(args, dry_run)
    print(f"[INFO] 動作モード: {mode}")
    if dry_run:
        print("[INFO] DRY-RUN: スプレッドシートへの書き込みはスキップします")
    if args.mock_llm:
        print("[INFO] MOCK-LLM: Gemini API をモック化します")
    if args.mock_sheets:
        print("[INFO] MOCK-SHEETS: MockSheetsClient を強制使用します")
    if args.use_sheets and args.test_write:
        print("[INFO] TEST-WRITE: Sheets への実書き込みを行います（SNS 投稿はしません）")

    # 設定読み込み
    if args.use_sheets:
        try:
            cfg = get_config()
        except ValueError as e:
            print(f"[ERROR] --use-sheets が指定されましたが認証情報が未設定です: {e}")
            sys.exit(1)
        force_mock = False
    else:
        cfg = get_config_partial()
        force_mock = args.mock_sheets

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    sheets = make_client(cfg, dry_run=dry_run, force_mock=force_mock)

    publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").strip().lower() in ("1", "true", "yes")

    print("\n" + "=" * 60)
    print(f"Phase 2 Pipeline 開始 [{mode}]")
    print("-" * 60)
    _print_mode_status(
        mode=mode,
        dry_run=dry_run,
        use_sheets=args.use_sheets,
        test_write=args.test_write,
        mock_llm=args.mock_llm,
        force_mock=force_mock,
        publish_enabled=publish_enabled,
    )
    print("=" * 60)

    # ---- Step 1: 下書き生成 ----
    print("\n[Step 1] draft 生成")
    try:
        drafts = generate_drafts(
            sheets=sheets,
            account_id=args.account_id,
            limit=args.limit,
            dry_run=dry_run,
        )
        print(f"[Step 1] 完了: {len(drafts)} 件生成")
    except Exception as e:
        print(f"[Step 1] ERROR: {e}")
        drafts = []

    # ---- Step 2: 派生投稿生成 ----
    print("\n[Step 2] social_derivative 生成")
    try:
        derivatives = generate_social_derivatives(
            sheets=sheets,
            account_id=args.account_id,
            platforms=platforms,
            status=["READY", "DRAFT"],
            limit=args.limit * len(platforms),
            dry_run=dry_run,
        )
        print(f"[Step 2] 完了: {len(derivatives)} 件生成")
    except Exception as e:
        print(f"[Step 2] ERROR: {e}")
        derivatives = []

    # ---- Step 3: queue 構築 ----
    print("\n[Step 3] queue 構築")
    try:
        queue_items = build_queue(
            sheets=sheets,
            account_id=args.account_id,
            platforms=platforms,
            dry_run=dry_run,
        )
        print(f"[Step 3] 完了: {len(queue_items)} 件追加")
    except Exception as e:
        print(f"[Step 3] ERROR: {e}")
        queue_items = []

    print("\n" + "=" * 60)
    print("Pipeline 完了サマリー")
    print(f"  動作モード:       {mode}")
    print(f"  drafts 生成:      {len(drafts)} 件")
    print(f"  derivatives 生成: {len(derivatives)} 件")
    print(f"  queue 追加:       {len(queue_items)} 件")
    if dry_run:
        print("  ※ DRY-RUN のため本番スプレッドシートへの書き込みは行っていません")
    print("  ※ 本番SNS投稿はまだ行いません（Phase 3で実装予定）")
    print("=" * 60)


def _detect_mode(args, dry_run: bool) -> str:
    if args.use_sheets and args.test_write:
        return "Mode D (full real + test write)"
    if args.dry_run and args.use_sheets:
        return "Mode C (Gemini実 + Sheets読み取りのみ)"
    if args.mock_llm:
        return "Mode A (full mock)"
    if dry_run:
        return "Mode B (Gemini実 + 書き込みなし)"
    return "カスタム"


def _print_mode_status(
    mode: str,
    dry_run: bool,
    use_sheets: bool,
    test_write: bool,
    mock_llm: bool,
    force_mock: bool,
    publish_enabled: bool,
) -> None:
    """実行時のモード設定を表形式で表示する。"""
    llm_mode = "MOCK_LLM" if mock_llm else "REAL_LLM"
    if force_mock:
        sheets_mode = "MOCK_SHEETS"
    elif use_sheets and not dry_run:
        sheets_mode = "REAL_SHEETS_WRITE (test-only)"
    elif use_sheets:
        sheets_mode = "REAL_SHEETS_READONLY"
    else:
        sheets_mode = "MOCK_SHEETS (フォールバック)"

    print(f"  MODE:             {llm_mode} + {sheets_mode}")
    print(f"  DRY_RUN:          {'true' if dry_run else 'false'}")
    print(f"  SHEETS_WRITE:     {'false (dry-run)' if dry_run else ('test-only' if test_write else 'false')}")
    print(f"  PUBLISH_ENABLED:  {'true ⚠' if publish_enabled else 'false'}")
    print(f"  SNS_POSTING:      {'ENABLED ⚠ (Phase 3)' if publish_enabled else 'disabled (安全)'}")


if __name__ == "__main__":
    main()
