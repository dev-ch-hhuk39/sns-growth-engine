"""
publish_queue.py - キュー投稿処理（Phase 3-D: dry-run + X 実投稿対応）

queue に積まれた投稿候補を検証・投稿する。

動作モード:
  --dry-run モード（デフォルト・推奨）:
    DryRunPublisher でテキスト検証のみ。実 SNS 投稿なし。

  --confirm-real-post モード（Phase 3-D: X のみ）:
    XPublisher で実際に X に投稿する。以下の条件がすべて必要:
      1. --confirm-real-post フラグ
      2. --max-real-posts N (N ≥ 1)
      3. PUBLISH_ENABLED=true (.env)
      4. ALLOW_REAL_X_POST=true (.env)
      5. X OAuth 1.0a 認証情報4項目設定済み (.env)
      6. --status READY (WAITING_REVIEW は不可)
      7. platform=x のみ（Threads は Phase 3-E）

安全停止:
  - --dry-run も --confirm-real-post もなければ即座に exit(1)
  - ALLOW_REAL_THREADS_POST=true は Threads 未実装のため常に警告停止
  - --max-real-posts 0 のまま --confirm-real-post は実行不可

使い方:
  # dry-run（推奨）
  python scripts/publish_queue.py \\
    --account-id night_scout \\
    --platform x --status WAITING_REVIEW \\
    --dry-run

  # X 実投稿（Phase 3-D 手動テスト）
  python scripts/publish_queue.py \\
    --account-id night_scout \\
    --platform x --status READY --limit 1 \\
    --confirm-real-post --queue-id <queue_id> --max-real-posts 1
"""
from __future__ import annotations

import argparse
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

from config_loader import get_config, get_config_partial
from sheets_client import SheetsClient, MockSheetsClient, make_client
from publishers.factory import get_publisher


def _fetch_queue(sheets, account_id: str | None, platforms: list[str],
                 status: str, limit: int | None, queue_id_filter: str | None = None) -> list[dict]:
    """queue タブから対象アイテムを取得する。"""
    if hasattr(sheets, "_sh"):
        ws = sheets._sh.worksheet("queue")
        rows = ws.get_all_records()
    else:
        rows = list(getattr(sheets, "_queue", []))

    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]
    if platforms:
        rows = [r for r in rows if str(r.get("platform", "")).lower() in platforms]
    rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
    if queue_id_filter:
        rows = [r for r in rows if r.get("queue_id") == queue_id_filter]
    if limit:
        rows = rows[:limit]
    return [dict(r) for r in rows]


def _fetch_derivative(sheets, draft_id: str, platform: str) -> dict:
    result = sheets.find_social_derivative(draft_id, platform)
    return result or {}


def _fetch_account(sheets, account_id: str) -> dict:
    result = sheets.get_account(account_id)
    return result or {"account_id": account_id}


def _truncate(text: str, n: int = 80) -> str:
    return text[:n] + "..." if len(text) > n else text


def _now_jst() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="キュー投稿処理 Phase 3-D"
    )
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--platform", help="単一プラットフォーム指定 (x / threads)")
    parser.add_argument("--platforms", default="x,threads",
                        help="複数プラットフォーム（カンマ区切り）")
    parser.add_argument("--status", default="WAITING_REVIEW",
                        help="対象 queue.status（デフォルト: WAITING_REVIEW）")
    parser.add_argument("--limit", type=int, help="処理上限件数")
    parser.add_argument("--dry-run", action="store_true",
                        help="dry-run モード（実投稿なし）")
    parser.add_argument("--confirm-real-post", action="store_true",
                        help="実投稿モードを有効化（--dry-run なしの場合に必須）")
    parser.add_argument("--queue-id", dest="queue_id_filter",
                        help="特定 queue_id のみ処理（実投稿モード用）")
    parser.add_argument("--max-real-posts", type=int, default=0,
                        help="実投稿の最大件数（デフォルト=0: 投稿しない）")
    parser.add_argument("--use-sheets", action="store_true",
                        help="実 SheetsClient を使用（認証情報必須）")
    parser.add_argument("--mock", action="store_true",
                        help="MockSheetsClient を強制使用")
    args = parser.parse_args()

    # ---- 安全停止: --dry-run か --confirm-real-post のいずれかが必須 ----
    if not args.dry_run and not args.confirm_real_post:
        print("[ERROR] --dry-run は必須です（実投稿する場合は --confirm-real-post を使用）。")
        print("  通常の検証: python scripts/publish_queue.py --account-id <id> --dry-run")
        print("  実投稿(Phase 3-D): python scripts/publish_queue.py \\")
        print("    --account-id <id> --platform x --status READY --limit 1 \\")
        print("    --confirm-real-post --queue-id <qid> --max-real-posts 1")
        sys.exit(1)

    if args.dry_run:
        _run_dry_mode(args)
    else:
        _run_real_post_mode(args)


def _run_dry_mode(args) -> None:
    """dry-run モード: DryRunPublisher でテキスト検証のみ。"""
    allow_threads = os.environ.get("ALLOW_REAL_THREADS_POST", "false").strip().lower()
    if allow_threads in ("1", "true", "yes"):
        print("[ERROR] ALLOW_REAL_THREADS_POST=true が検出されました。")
        print("  Threads への本番投稿は Phase 3-E まで実施しません。")
        print("  .env の ALLOW_REAL_THREADS_POST を false に戻してください。")
        sys.exit(1)

    publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").strip().lower()
    allow_x = os.environ.get("ALLOW_REAL_X_POST", "false").strip().lower()

    print("=" * 60)
    print("  publish_queue.py - Phase 3-D dry-run モード")
    print("=" * 60)
    print("[INFO] DRY-RUN: 実 SNS 投稿は行いません")
    print("[INFO] posted_results への書き込みなし")
    print("[INFO] queue.status の変更なし")

    # ---- プラットフォーム解決 ----
    if args.platform:
        platforms = [args.platform.strip().lower()]
    else:
        platforms = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]

    # ---- Sheets クライアント初期化 ----
    sheets = _init_sheets(args)
    account_label = args.account_id or "全アカウント"
    print(f"\n対象: {account_label} / platforms={platforms} / status={args.status}")
    if args.limit:
        print(f"  (上限: {args.limit}件)")

    # ---- 対象外 status の安全チェック ----
    excluded = {"REJECTED", "POSTED", "FAILED", "SKIPPED"}
    if args.status.upper() in excluded:
        print(f"[ERROR] status={args.status.upper()} は publish_queue の対象外です。")
        print(f"  対象: WAITING_REVIEW, READY")
        sys.exit(1)

    queue_items = _fetch_queue(
        sheets, args.account_id, platforms, args.status, args.limit,
        getattr(args, "queue_id_filter", None)
    )

    if not queue_items:
        print(f"\n[INFO] 対象キューアイテムなし (status={args.status})")
        sheets.log(
            operation="publish_queue",
            status="OK",
            message=f"dry-run: 対象キューアイテムなし (status={args.status})",
            account_id=args.account_id or "",
            level="INFO",
        )
        print("\n[RESULT] 処理対象なし。正常終了。")
        sys.exit(0)

    print(f"\n{len(queue_items)}件のキューアイテムを処理します。\n")

    ok_count = 0
    warn_count = 0
    fail_count = 0

    for q in queue_items:
        queue_id = q.get("queue_id", "?")
        draft_id = q.get("draft_id", "")
        platform = str(q.get("platform", "")).lower()
        account_id = q.get("account_id", args.account_id or "")

        print(f"{'─' * 55}")
        print(f"  queue_id : {queue_id}")
        print(f"  platform : {platform.upper()}")
        print(f"  account  : {account_id}")
        print(f"  draft_id : {draft_id}")

        account = _fetch_account(sheets, account_id)
        derivative = _fetch_derivative(sheets, draft_id, platform) if draft_id else {}

        if not derivative:
            print(f"  [WARN] social_derivative が見つかりません (draft_id={draft_id} platform={platform})")
            warn_count += 1
            sheets.log(
                operation="publish_queue",
                status="WARN",
                message=f"dry-run: derivative not found queue_id={queue_id}",
                account_id=account_id,
                level="WARN",
            )
            continue

        text = str(derivative.get("text", ""))
        char_count = len(text)
        print(f"  文字数   : {char_count}字")
        print(f"  text     : {_truncate(text, 100)}")

        publisher = get_publisher(platform=platform, dry_run=True)
        result = publisher.publish(
            text,
            account=account,
            derivative=derivative,
            queue_item=q,
            dry_run=True,
        )

        if result.success:
            tag = "[DRY_RUN/OK]"
            ok_count += 1
            log_status = "OK"
            log_level = "INFO"
        else:
            tag = "[DRY_RUN/FAIL]"
            fail_count += 1
            log_status = "FAIL"
            log_level = "ERROR"

        if "WARN" in result.message:
            warn_count += 1

        print(f"  {tag} {result.message}")

        sheets.log(
            operation="publish_queue",
            status=log_status,
            message=f"dry-run publish check: {result.message}",
            account_id=account_id,
            level=log_level,
        )

    # ---- サマリー ----
    print(f"\n{'─' * 55}")
    print(f"{'=' * 60}")
    print("dry-run publish チェック サマリー:")
    print(f"  合計    : {len(queue_items)}件")
    print(f"  OK      : {ok_count}件")
    print(f"  WARN含む: {warn_count}件")
    print(f"  FAIL    : {fail_count}件")
    print()
    print("確認事項:")
    print("  [√] 実 SNS 投稿: なし")
    print("  [√] posted_results 書き込み: なし")
    print("  [√] queue.status 変更: なし")
    print(f"  [√] PUBLISH_ENABLED: {publish_enabled}")
    print(f"  [√] ALLOW_REAL_X_POST: {allow_x}")
    print(f"  [√] ALLOW_REAL_THREADS_POST: {allow_threads} (安全)")
    print("=" * 60)

    if fail_count > 0:
        print(f"\n[RESULT] {fail_count}件の投稿テキストに問題があります。修正後に再確認してください。")
        sys.exit(1)
    else:
        print(f"\n[RESULT] dry-run チェック完了。全{ok_count}件が投稿可能です（実投稿は --confirm-real-post で）。")
        sys.exit(0)


def _run_real_post_mode(args) -> None:
    """実投稿モード（Phase 3-D: X のみ）。"""
    print("=" * 60)
    print("  publish_queue.py - Phase 3-D 実投稿モード（X）")
    print("=" * 60)

    # ---- 安全ガード: PUBLISH_ENABLED ----
    publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").strip().lower()
    if publish_enabled not in ("1", "true", "yes"):
        print("[ERROR] PUBLISH_ENABLED=false です。実投稿には PUBLISH_ENABLED=true が必要です。")
        print("  Phase 3-D の手動テスト時のみ .env で true に設定してください。")
        sys.exit(1)

    # ---- 安全ガード: ALLOW_REAL_X_POST ----
    allow_x = os.environ.get("ALLOW_REAL_X_POST", "false").strip().lower()
    if allow_x not in ("1", "true", "yes"):
        print("[ERROR] ALLOW_REAL_X_POST=false です。実投稿には ALLOW_REAL_X_POST=true が必要です。")
        print("  Phase 3-D の手動テスト時のみ .env で true に設定してください。")
        sys.exit(1)

    # ---- 安全ガード: ALLOW_REAL_THREADS_POST（Threads 未実装のため常に停止）----
    allow_threads = os.environ.get("ALLOW_REAL_THREADS_POST", "false").strip().lower()
    if allow_threads in ("1", "true", "yes"):
        print("[ERROR] ALLOW_REAL_THREADS_POST=true が検出されました。")
        print("  Threads への本番投稿は Phase 3-E まで実施しません。")
        sys.exit(1)

    # ---- 安全ガード: --max-real-posts > 0 が必要 ----
    if args.max_real_posts <= 0:
        print("[ERROR] --max-real-posts に 1 以上の値が必要です（デフォルト=0: 投稿しない）。")
        print("  例: --max-real-posts 1")
        sys.exit(1)

    # ---- プラットフォーム確認（X のみ）----
    if args.platform:
        platforms = [args.platform.strip().lower()]
    else:
        platforms = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]

    non_x = [p for p in platforms if p != "x"]
    if non_x:
        print(f"[ERROR] 実投稿モードは現在 X のみ対応しています。未対応プラットフォーム: {non_x}")
        print("  --platform x を指定してください。Threads は Phase 3-E 以降。")
        sys.exit(1)

    # ---- status=READY が必要 ----
    if args.status.upper() != "READY":
        print(f"[ERROR] 実投稿モードは --status READY が必要です（現在: {args.status}）。")
        print("  承認済みアイテムのみ実投稿できます。")
        print("  python scripts/approve_queue.py --queue-id <id> --approve --reason <reason>")
        sys.exit(1)

    print(f"[INFO] PUBLISH_ENABLED=true / ALLOW_REAL_X_POST=true 確認済み")
    print(f"[INFO] 実投稿上限: {args.max_real_posts}件")
    if args.queue_id_filter:
        print(f"[INFO] 対象 queue_id: {args.queue_id_filter}")

    # ---- Sheets クライアント初期化 ----
    sheets = _init_sheets(args)
    account_label = args.account_id or "全アカウント"
    print(f"\n対象: {account_label} / platforms=x / status=READY")
    if args.limit:
        print(f"  (上限: {args.limit}件)")

    queue_items = _fetch_queue(
        sheets, args.account_id, ["x"], "READY", args.limit,
        args.queue_id_filter
    )

    if not queue_items:
        print(f"\n[INFO] 対象キューアイテムなし (status=READY, platform=x)")
        sheets.log(
            operation="publish_queue",
            status="OK",
            message="real-post: 対象キューアイテムなし",
            account_id=args.account_id or "",
            level="INFO",
        )
        print("\n[RESULT] 処理対象なし。正常終了。")
        sys.exit(0)

    print(f"\n{len(queue_items)}件の READY アイテムが見つかりました。")
    print(f"最大 {args.max_real_posts}件を実際に X に投稿します。\n")

    ok_count = 0
    fail_count = 0
    real_count = 0
    publisher = get_publisher(platform="x", dry_run=False)

    for q in queue_items:
        if real_count >= args.max_real_posts:
            print(f"\n[INFO] 実投稿上限 ({args.max_real_posts}件) に達したため終了します。")
            break

        queue_id = q.get("queue_id", "?")
        draft_id = q.get("draft_id", "")
        platform = str(q.get("platform", "")).lower()
        account_id = q.get("account_id", args.account_id or "")

        print(f"{'─' * 55}")
        print(f"  queue_id : {queue_id}")
        print(f"  platform : {platform.upper()}")
        print(f"  account  : {account_id}")
        print(f"  draft_id : {draft_id}")

        # draft_only アカウントは実投稿禁止
        try:
            from accounts.account_config import load_account_config
            acct_cfg = load_account_config(account_id)
            if acct_cfg.is_draft_only():
                print(f"  [BLOCKED] {account_id} は draft_only アカウントです。実投稿はできません。")
                fail_count += 1
                sheets.log(
                    operation="publish_queue",
                    status="BLOCKED",
                    message=f"draft_only account blocked: {account_id} queue_id={queue_id}",
                    account_id=account_id,
                    level="ERROR",
                )
                continue
        except FileNotFoundError:
            pass

        # 重複投稿防止: queue.status が POSTED でないことを再確認
        if str(q.get("status", "")).upper() == "POSTED":
            print(f"  [SKIP] 既に POSTED 済みです。スキップします。")
            continue

        account = _fetch_account(sheets, account_id)
        derivative = _fetch_derivative(sheets, draft_id, platform) if draft_id else {}
        derivative_id = derivative.get("derivative_id", "")

        if not derivative:
            print(f"  [WARN] social_derivative が見つかりません (draft_id={draft_id} platform={platform})")
            sheets.log(
                operation="publish_queue",
                status="WARN",
                message=f"real-post: derivative not found queue_id={queue_id}",
                account_id=account_id,
                level="WARN",
            )
            fail_count += 1
            continue

        text = str(derivative.get("text", ""))
        char_count = len(text)
        print(f"  文字数   : {char_count}字")
        print(f"  text     : {_truncate(text, 100)}")

        # ---- 実投稿 ----
        print(f"\n  [POSTING] X に投稿します...")
        result = publisher.publish(
            text,
            account=account,
            derivative=derivative,
            queue_item=q,
            dry_run=False,
        )

        if result.success:
            real_count += 1
            ok_count += 1
            processed_at = _now_jst()
            print(f"  [OK] {result.message}")

            # queue.status を POSTED に更新
            sheets.update_queue_item(queue_id, status="POSTED", processed_at=processed_at)

            # posted_results に記録
            manual_memo = (
                f"x manual test post"
                f" | queue_id={queue_id}"
                f" | derivative_id={derivative_id}"
                f" | external_post_id={result.external_post_id or ''}"
                f" | platform=x"
                f" | account={account_id}"
            )
            sheets.save_result(
                draft_id=draft_id,
                account_id=account_id,
                note_url=result.posted_url or "",
                manual_memo=manual_memo,
                posted_at=processed_at,
            )

            sheets.log(
                operation="publish_queue",
                status="OK",
                message=(
                    f"X投稿成功 queue_id={queue_id}"
                    f" tweet_id={result.external_post_id}"
                    f" url={result.posted_url}"
                ),
                account_id=account_id,
                level="INFO",
            )

        else:
            fail_count += 1
            error_msg = result.message
            print(f"  [FAIL] {error_msg}")

            # queue.error に失敗メッセージを記録（status は READY のまま）
            sheets.update_queue_item(queue_id, error=_truncate(error_msg, 200))

            sheets.log(
                operation="publish_queue",
                status="ERROR",
                message=f"X投稿失敗 queue_id={queue_id}: {_truncate(error_msg, 150)}",
                account_id=account_id,
                level="ERROR",
            )

    # ---- サマリー ----
    print(f"\n{'─' * 55}")
    print(f"{'=' * 60}")
    print("実投稿 サマリー:")
    print(f"  対象    : {len(queue_items)}件")
    print(f"  投稿成功: {ok_count}件")
    print(f"  失敗    : {fail_count}件")
    print(f"  投稿実施: {real_count}件 / 上限 {args.max_real_posts}件")
    print("=" * 60)

    if fail_count > 0:
        print(f"\n[RESULT] {fail_count}件の投稿に失敗しました。ログを確認してください。")
        sys.exit(1)
    else:
        print(f"\n[RESULT] 投稿完了。{ok_count}件が正常に X に投稿されました。")
        sys.exit(0)


def _init_sheets(args):
    """引数に応じて Sheets クライアントを初期化する。"""
    if args.mock:
        sheets = MockSheetsClient(dry_run=args.dry_run)
        print("[INFO] MockSheetsClient を使用します")
        return sheets
    if args.use_sheets:
        try:
            cfg = get_config()
        except ValueError as e:
            print(f"[ERROR] 認証情報が必要です: {e}")
            sys.exit(1)
        return SheetsClient(
            sheet_id=cfg["sheet_id"],
            sa_dict=cfg["sa_dict"],
            dry_run=args.dry_run,
        )
    cfg = get_config_partial()
    return make_client(cfg, dry_run=args.dry_run, force_mock=False)


if __name__ == "__main__":
    main()
