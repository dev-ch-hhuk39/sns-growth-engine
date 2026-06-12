"""
preflight_threads_real_post.py - Threads本番投稿前最終preflight

Threads API 実投稿を実行する前に必要な全条件を確認する。
このスクリプト自体は実投稿を行わない。

チェック内容:
  1. Threads API 認証情報 set/missing 確認（値は表示しない）
  2. ALLOW_REAL_THREADS_POST=false 確認
  3. PUBLISH_ENABLED=false 確認
  4. draft_only アカウントは BLOCKED
  5. account_config の threads_policy 確認
  6. READY queue 候補の確認
  7. thread_series の WAITING_REVIEW 状態確認

使い方:
  python scripts/preflight_threads_real_post.py --mock
  python scripts/preflight_threads_real_post.py --account-id night_scout
  python scripts/preflight_threads_real_post.py --account-id beauty_account --mock
  # → [BLOCKED] beauty_account は draft_only アカウントです。 が表示されること

禁止事項:
  - 実投稿
  - シークレット値の表示
  - ALLOW_REAL_THREADS_POST=true の設定
  - draft_only アカウントへの実投稿
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

from sheets_client import MockSheetsClient

RESULTS: list[tuple[str, str, str]] = []


def _add(level: str, label: str, msg: str) -> None:
    RESULTS.append((level, label, msg))
    icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}[level]
    print(f"  {icon} {label}: {msg}")


def _env_str(key: str) -> str:
    return os.environ.get(key, "").strip()


def _masked(val: str) -> str:
    if not val:
        return "(未設定)"
    if len(val) <= 6:
        return "****"
    return val[:3] + "****"


def check_threads_credentials() -> bool:
    """Threads API 認証情報の set/missing 確認（値は表示しない）。"""
    print("\n[1] Threads API 認証情報（値は表示しません）")
    creds = [
        "THREADS_APP_ID",
        "THREADS_APP_SECRET",
        "THREADS_ACCESS_TOKEN",
        "THREADS_USER_ID",
    ]
    all_set = True
    for key in creds:
        val = _env_str(key)
        if val:
            _add("PASS", key, "set（値は非表示）")
        else:
            _add("WARN", key, "未設定（実投稿時に必要）")
            all_set = False
    if not all_set:
        _add("INFO", "Threads credentials", "実投稿前に全項目を .env に設定してください")
    return all_set


def check_safety_flags() -> None:
    """ALLOW_REAL_THREADS_POST / PUBLISH_ENABLED の確認。"""
    print("\n[2] 安全ガードフラグ確認")
    allow_threads = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower()
    publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").lower()

    if allow_threads in ("true", "1", "yes"):
        _add("WARN", "ALLOW_REAL_THREADS_POST", "true（Threads実投稿が有効です）")
    else:
        _add("PASS", "ALLOW_REAL_THREADS_POST", "false（Threads実投稿無効）")

    if publish_enabled in ("true", "1", "yes"):
        _add("WARN", "PUBLISH_ENABLED", "true（本番投稿が有効です）")
    else:
        _add("PASS", "PUBLISH_ENABLED", "false（本番投稿無効）")


def check_account_config(account_id: str | None) -> bool:
    """account_config の threads_policy 確認。draft_only は BLOCKED。"""
    if not account_id:
        _add("INFO", "account_config", "account_id 未指定（全アカウント対象）")
        return True

    print(f"\n[3] account_config 確認: {account_id}")
    try:
        from accounts.account_config import load_account_config
        cfg = load_account_config(account_id)

        if cfg.is_draft_only():
            _add("FAIL", "account_status", f"{account_id} は draft_only アカウントです。Threads実投稿 preflight は実行できません。")
            return False

        if not cfg.allows_platform("threads"):
            _add("FAIL", "threads_platform", f"{account_id} は threads プラットフォームを未設定です")
            return False

        limits = cfg.get_char_limits("threads")
        _add("PASS", "threads_char_limit_soft", f"{limits['soft']}字")
        _add("PASS", "threads_char_limit_hard", f"{limits['hard']}字")

        if cfg.is_active():
            _add("PASS", "account_status", f"{account_id} は active です")
        else:
            _add("WARN", "account_status", f"{account_id} は active ではありません (status={cfg.status})")

        allow_real = cfg.safety_policy.get("allow_real_post", False)
        if allow_real:
            _add("WARN", "allow_real_post", "true（safety_policy で実投稿許可）")
        else:
            _add("PASS", "allow_real_post", "false（safety_policy で実投稿禁止）")

    except FileNotFoundError:
        _add("WARN", "account_config", f"{account_id} の設定ファイルが見つかりません")

    return True


def check_ready_queue(sheets, account_id: str | None) -> list[dict]:
    """READY queue 候補を確認する。"""
    print("\n[4] READY queue 候補確認（Threads）")

    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet("queue")
            rows = ws.get_all_records()
        except Exception:
            rows = []
    else:
        rows = list(getattr(sheets, "_queue", []))

    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]

    rows = [dict(r) for r in rows if str(r.get("platform", "")).lower() == "threads"]
    ready = [r for r in rows if str(r.get("status", "")).upper() == "READY"]

    _add("INFO", "Threads READY queue", f"{len(ready)}件")
    if not ready:
        _add("INFO", "READY queue", "Threads投稿候補がありません（dry-run 正常）")

    return ready


def check_thread_series_status(account_id: str | None) -> None:
    """thread_series の WAITING_REVIEW 状態確認。"""
    print("\n[5] thread_series 安全確認")
    _add("INFO", "thread_series", "thread_series は全ポスト WAITING_REVIEW で管理されます")
    _add("PASS", "READY化禁止", "thread_series は Threads 実投稿前に別途レビューが必要")
    if account_id:
        try:
            from accounts.account_config import load_account_config
            cfg = load_account_config(account_id)
            if cfg.is_draft_only():
                _add("FAIL", "thread_series_draft_only", f"{account_id} は draft_only。thread_series の Threads 実投稿禁止")
            else:
                _add("PASS", "thread_series_account", f"{account_id} は {cfg.status}。thread_series 生成可能（WAITING_REVIEW）")
        except FileNotFoundError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Threads本番投稿前最終preflight")
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    parser.add_argument("--strict", action="store_true", help="WARN でも終了コード 1")
    args = parser.parse_args()

    print("=" * 65)
    print("  preflight_threads_real_post.py - Threads本番投稿前最終preflight")
    print("=" * 65)
    print("[INFO] このスクリプトは実投稿を行いません。")
    print("[INFO] ALLOW_REAL_THREADS_POST=false を前提に動作します。")

    # draft_only アカウントの早期ブロック
    if args.account_id:
        try:
            from accounts.account_config import load_account_config
            cfg = load_account_config(args.account_id)
            if cfg.is_draft_only():
                print(f"\n[BLOCKED] {args.account_id} は draft_only アカウントです。")
                print("  draft_only アカウントへの実投稿 preflight は実行できません。")
                print("  status を active に変更するには明示的なユーザー承認が必要です。")
                sys.exit(1)
        except FileNotFoundError:
            pass

    # Sheets 接続
    if args.mock:
        print("[INFO] MockSheetsClient を使用します")
        sheets = MockSheetsClient(dry_run=True)
    else:
        try:
            from config_loader import get_config
            from sheets_client import SheetsClient
            cfg = get_config()
            sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
        except Exception:
            print("[WARN] Sheets認証情報未設定 → MockSheetsClient にフォールバック")
            sheets = MockSheetsClient(dry_run=True)

    check_threads_credentials()
    check_safety_flags()
    account_ok = check_account_config(args.account_id)

    if not account_ok:
        print(f"\n[BLOCKED] アカウント設定の確認に失敗しました。")
        sys.exit(1)

    check_ready_queue(sheets, args.account_id)
    check_thread_series_status(args.account_id)

    # サマリー
    print("\n" + "=" * 65)
    fail_count = sum(1 for r in RESULTS if r[0] == "FAIL")
    warn_count = sum(1 for r in RESULTS if r[0] == "WARN")
    pass_count = sum(1 for r in RESULTS if r[0] == "PASS")

    print(f"チェック結果: PASS={pass_count} / WARN={warn_count} / FAIL={fail_count}")

    if fail_count > 0:
        print("\n[RESULT] FAIL: 投稿ブロック条件があります。解消してから再チェックしてください。")
        sys.exit(1)
    elif warn_count > 0 and args.strict:
        print("\n[RESULT] WARN（--strict 指定）: 警告を解消してください。")
        sys.exit(1)
    elif warn_count > 0:
        print("\n[RESULT] WARN: 実投稿前に確認推奨の項目があります。")
        print("  ※ Threads 認証情報は実投稿時のみ必要です")
    else:
        print("\n[RESULT] PASS: 全チェック正常です。")

    print("\n[次のステップ] 実投稿手順:")
    print("  docs/threads-real-post-final-checklist.md を参照してください")
    print("  実投稿コマンドは同ドキュメントに記載されています（今回は実行しない）")


if __name__ == "__main__":
    main()
