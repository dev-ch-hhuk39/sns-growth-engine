"""
main.py - SNS統合スプレッドシート v2 エントリーポイント

【Phase 1 コマンド】
  python src/main.py --setup-only            # タブ初期化のみ
  python src/main.py --dry-run               # dry-run確認

【Phase 2 コマンド】
  python src/main.py --generate-drafts --account-id night_scout --limit 5 --dry-run --mock-llm
  python src/main.py --generate-derivatives --account-id night_scout --platforms x,threads --dry-run --mock-llm
  python src/main.py --build-queue --account-id night_scout --platforms x,threads --dry-run
  python src/main.py --run-pipeline --account-id night_scout --platforms x,threads --limit 5 --dry-run --mock-llm

【Phase 2.5 コマンド (追加フラグ)】
  --mock-sheets   : Sheets を MockSheetsClient に強制切替
  --use-sheets    : 実際の SheetsClient を使用（認証情報必須）
  --test-write    : Sheets に実際に書き込む（--use-sheets が必要、SNS投稿はしない）

  本番SNS投稿はPhase 3以降。PUBLISH_ENABLED=false の間は投稿処理は実行されない。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config_loader import get_config, get_config_partial
from sheets_client import make_client, SheetsClient


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 統合スプレッドシートシステム")
    # Phase 1
    parser.add_argument("--dry-run", action="store_true", help="書き込みをスキップ")
    parser.add_argument("--setup-only", action="store_true", help="タブ初期化のみ実行して終了")
    # Phase 2
    parser.add_argument("--generate-drafts", action="store_true", help="下書き生成")
    parser.add_argument("--generate-derivatives", action="store_true", help="派生投稿生成")
    parser.add_argument("--build-queue", action="store_true", help="queue 構築")
    parser.add_argument("--run-pipeline", action="store_true", help="パイプライン全体を実行")
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--platforms", default="x,threads", help="対象プラットフォーム（カンマ区切り）")
    parser.add_argument("--limit", type=int, default=5, help="生成件数")
    parser.add_argument("--mock-llm", action="store_true", help="LLM 呼び出しをモック化")
    # Phase 2.5
    parser.add_argument("--mock-sheets", action="store_true", help="Sheets を MockSheetsClient に強制切替")
    parser.add_argument("--use-sheets", action="store_true", help="実際のSheetsClientを使用（認証情報必須）")
    parser.add_argument("--test-write", action="store_true", help="Sheetsテスト書き込み（--use-sheetsが必要）")
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

    if args.mock_llm:
        os.environ["MOCK_LLM"] = "true"
    if args.mock_sheets:
        os.environ["MOCK_SHEETS"] = "true"

    if args.test_write:
        dry_run = False
    else:
        dry_run = args.dry_run or os.environ.get("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")

    if dry_run:
        print("[INFO] DRY-RUN モードで実行します（書き込みは行いません）")

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

    client = make_client(cfg, dry_run=dry_run, force_mock=force_mock)
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    # ---- Phase 2: パイプライン ----
    if args.run_pipeline:
        _run_pipeline(client, args.account_id, platforms, args.limit, dry_run)
        return

    if args.generate_drafts:
        _run_generate_drafts(client, args.account_id, args.limit, dry_run)
        return

    if args.generate_derivatives:
        _run_generate_derivatives(client, args.account_id, platforms, args.limit, dry_run)
        return

    if args.build_queue:
        _run_build_queue(client, args.account_id, platforms, dry_run)
        return

    # ---- --test-write: Sheets テスト書き込み ----
    if args.test_write:
        _run_test_write(client)
        return

    # ---- Phase 1: セットアップ ----
    print("[INFO] タブ初期化を実行します")
    try:
        client.setup_all()
    except Exception as e:
        client.log("setup_all", "ERROR", str(e))
        print(f"[ERROR] セットアップ失敗: {e}")
        sys.exit(1)

    if args.setup_only:
        print("[INFO] --setup-only のため終了します")
        return

    client.log("main", "INFO", "v2 起動確認", details="Phase 2 パイプライン準備完了")
    print("[INFO] 起動確認完了。--run-pipeline でパイプラインを実行できます。")


# ------------------------------------------------------------------ #
# Phase 2 実行関数
# ------------------------------------------------------------------ #

def _run_pipeline(client, account_id, platforms, limit, dry_run):
    from draft_generator import generate_drafts
    from social_derivative_generator import generate_social_derivatives
    from queue_builder import build_queue

    print("\n[Pipeline] Step 1: draft 生成")
    drafts = generate_drafts(sheets=client, account_id=account_id, limit=limit, dry_run=dry_run)

    print("\n[Pipeline] Step 2: social_derivative 生成")
    ders = generate_social_derivatives(
        sheets=client, account_id=account_id,
        platforms=platforms, status=["READY", "DRAFT"],
        limit=limit * len(platforms), dry_run=dry_run,
    )

    print("\n[Pipeline] Step 3: queue 構築")
    q = build_queue(sheets=client, account_id=account_id, platforms=platforms, dry_run=dry_run)

    print(f"\n[Pipeline] 完了: drafts={len(drafts)} derivatives={len(ders)} queue={len(q)}")
    print("  ※ 本番SNS投稿はまだ行いません（Phase 3で実装予定）")


def _run_generate_drafts(client, account_id, limit, dry_run):
    from draft_generator import generate_drafts
    drafts = generate_drafts(sheets=client, account_id=account_id, limit=limit, dry_run=dry_run)
    print(f"\n[DONE] draft 生成: {len(drafts)} 件")


def _run_generate_derivatives(client, account_id, platforms, limit, dry_run):
    from social_derivative_generator import generate_social_derivatives
    ders = generate_social_derivatives(
        sheets=client, account_id=account_id,
        platforms=platforms, status=["READY", "DRAFT"],
        limit=limit * len(platforms), dry_run=dry_run,
    )
    print(f"\n[DONE] derivative 生成: {len(ders)} 件")


def _run_build_queue(client, account_id, platforms, dry_run):
    from queue_builder import build_queue
    q = build_queue(sheets=client, account_id=account_id, platforms=platforms, dry_run=dry_run)
    print(f"\n[DONE] queue 追加: {len(q)} 件")


# ------------------------------------------------------------------ #
# Phase 1 テスト書き込み
# ------------------------------------------------------------------ #

def _run_test_write(client) -> None:
    """接続確認用のサンプルデータを書き込む（--test-write 時のみ呼ばれる）。"""
    print("[test] save_draft を実行します")
    try:
        draft_id = client.save_draft(
            account_id="night_scout",
            title="【テスト】Phase 1 接続確認",
            body_md="# テスト\nこれはv2 Phase 1の接続確認用ダミー投稿です。",
            status="DRAFT",
            generation_model="gemini-2.5-flash",
            prompt_version="v1",
            post_mode="test",
        )
        print(f"[test] save_draft 完了: draft_id={draft_id}")
    except Exception as e:
        print(f"[ERROR] save_draft 失敗: {e}")
        client.log("test_write", "ERROR", f"save_draft失敗: {e}", account_id="night_scout")
        return

    try:
        result_id = client.save_result(
            draft_id=draft_id,
            account_id="night_scout",
            measurement_window="24h",
            views="0",
            likes="0",
            manual_memo="Phase 1 テスト用ダミーデータ",
        )
        print(f"[test] save_result 完了: result_id={result_id}")
    except Exception as e:
        print(f"[ERROR] save_result 失敗: {e}")

    try:
        client.log(
            operation="test_write",
            status="OK",
            message="Phase 1 接続確認テスト書き込み完了",
            account_id="night_scout",
            details=f"draft_id={draft_id}",
        )
        print("[test] log 完了")
    except Exception as e:
        print(f"[ERROR] log 失敗: {e}")

    print("[test] --test-write 完了")


if __name__ == "__main__":
    main()
