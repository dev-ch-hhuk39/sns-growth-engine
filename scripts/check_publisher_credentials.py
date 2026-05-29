"""
check_publisher_credentials.py - SNS Publisher 認証情報チェック（Phase 3-C）

X / Threads 本番投稿APIに必要な認証情報が揃っているか確認する。
API への接続は行わず、環境変数の存在確認のみを実施する。
値はログに出力しない。

使い方:
  python scripts/check_publisher_credentials.py
  python scripts/check_publisher_credentials.py --platform x
  python scripts/check_publisher_credentials.py --platform threads

判定:
  READY_FOR_DRY_RUN        - 安全ガードOK（投稿不可だが dry-run は可）
  READY_FOR_CREDENTIAL_TEST - 全認証情報がセット済み（投稿可能な設定）
  NOT_READY                 - 必須認証情報が不足している
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

from config_loader import get_x_credentials, get_threads_credentials, get_publish_guards


def _mark(is_set: bool) -> str:
    return "[set]    " if is_set else "[missing]"


def check_x(results: list[str]) -> tuple[bool, bool]:
    """X 認証情報チェック。(oauth1_ready, oauth2_ready) を返す。"""
    creds = get_x_credentials()
    results.append("  --- OAuth 1.0a (ユーザー投稿用・推奨) ---")
    results.append(f"  {_mark(creds['api_key_set'])} X_API_KEY")
    results.append(f"  {_mark(creds['api_secret_set'])} X_API_SECRET")
    results.append(f"  {_mark(creds['access_token_set'])} X_ACCESS_TOKEN")
    results.append(f"  {_mark(creds['access_token_secret_set'])} X_ACCESS_TOKEN_SECRET")
    oauth1_ready = all([
        creds["api_key_set"],
        creds["api_secret_set"],
        creds["access_token_set"],
        creds["access_token_secret_set"],
    ])
    results.append(f"  → OAuth 1.0a: {'OK (4項目セット済み)' if oauth1_ready else 'NG (不足あり)'}")

    results.append("")
    results.append("  --- OAuth 2.0 (代替方式) ---")
    results.append(f"  {_mark(creds['client_id_set'])} X_CLIENT_ID")
    results.append(f"  {_mark(creds['client_secret_set'])} X_CLIENT_SECRET")
    results.append(f"  {_mark(creds['oauth2_access_token_set'])} X_OAUTH2_ACCESS_TOKEN")
    results.append(f"  {_mark(creds['oauth2_refresh_token_set'])} X_OAUTH2_REFRESH_TOKEN")
    results.append(f"  {_mark(creds['redirect_uri_set'])} X_REDIRECT_URI (任意)")
    oauth2_ready = all([
        creds["client_id_set"],
        creds["client_secret_set"],
        creds["oauth2_access_token_set"],
    ])
    results.append(f"  → OAuth 2.0: {'OK (3項目セット済み)' if oauth2_ready else 'NG (不足あり)'}")

    results.append("")
    results.append(f"  {_mark(creds['bearer_token_set'])} X_BEARER_TOKEN (読み取り専用・投稿には不要)")

    return oauth1_ready, oauth2_ready


def check_threads(results: list[str]) -> bool:
    """Threads 認証情報チェック。ready フラグを返す。"""
    creds = get_threads_credentials()
    results.append(f"  {_mark(creds['access_token_set'])} THREADS_ACCESS_TOKEN")
    results.append(f"  {_mark(creds['user_id_set'])} THREADS_USER_ID")
    results.append(f"  {_mark(creds['app_id_set'])} THREADS_APP_ID")
    results.append(f"  {_mark(creds['app_secret_set'])} THREADS_APP_SECRET")
    results.append(f"  [set]     THREADS_API_VERSION = {creds['api_version']}")

    ready = all([
        creds["access_token_set"],
        creds["user_id_set"],
    ])
    results.append(f"  → Threads: {'OK (必須2項目セット済み)' if ready else 'NG (不足あり)'}")
    return ready


def check_guards(results: list[str]) -> bool:
    """安全ガード環境変数チェック。全て false なら True を返す。"""
    guards = get_publish_guards()
    publish_safe = not guards["publish_enabled"]
    x_safe = not guards["allow_real_x_post"]
    threads_safe = not guards["allow_real_threads_post"]

    pub_val = "false (安全)" if publish_safe else "TRUE (注意: Phase 3-D まで false を維持)"
    x_val = "false (安全)" if x_safe else "TRUE (注意: Phase 3-D の手動テスト時のみ)"
    t_val = "false (安全)" if threads_safe else "TRUE (注意: Phase 3-E の手動テスト時のみ)"

    results.append(f"  PUBLISH_ENABLED         = {pub_val}")
    results.append(f"  ALLOW_REAL_X_POST       = {x_val}")
    results.append(f"  ALLOW_REAL_THREADS_POST = {t_val}")
    return publish_safe and x_safe and threads_safe


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SNS Publisher 認証情報チェック（Phase 3-C）"
    )
    parser.add_argument(
        "--platform", choices=["x", "threads"],
        help="特定プラットフォームのみチェック（省略時: 両方）"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  check_publisher_credentials.py - 認証情報チェック")
    print("  Phase 3-C: APIへの接続は行いません")
    print("=" * 60)
    print("[INFO] 値の表示はしません（存在確認のみ）")
    print("[INFO] 本番投稿可能とは判定しません")
    print()

    results: list[str] = []
    x_ready = False
    threads_ready = False

    # ---- 安全ガード ----
    print("[安全ガード確認]")
    guard_results: list[str] = []
    guards_safe = check_guards(guard_results)
    for line in guard_results:
        print(line)
    print()

    # ---- X 認証情報 ----
    check_x_flag = args.platform is None or args.platform == "x"
    if check_x_flag:
        print("[X API 認証情報]")
        x_results: list[str] = []
        oauth1_ready, oauth2_ready = check_x(x_results)
        for line in x_results:
            print(line)
        x_ready = oauth1_ready or oauth2_ready
        print()

    # ---- Threads 認証情報 ----
    check_threads_flag = args.platform is None or args.platform == "threads"
    if check_threads_flag:
        print("[Threads API 認証情報]")
        threads_results: list[str] = []
        threads_ready = check_threads(threads_results)
        for line in threads_results:
            print(line)
        print()

    # ---- 総合判定 ----
    print("=" * 60)
    print("総合判定:")

    if check_x_flag:
        if x_ready:
            x_verdict = "READY_FOR_CREDENTIAL_TEST"
        else:
            x_verdict = "NOT_READY (認証情報不足)"
        print(f"  X       : {x_verdict}")

    if check_threads_flag:
        if threads_ready:
            threads_verdict = "READY_FOR_CREDENTIAL_TEST"
        else:
            threads_verdict = "NOT_READY (認証情報不足)"
        print(f"  Threads : {threads_verdict}")

    print()
    print("[安全ガード]")
    if guards_safe:
        print("  READY_FOR_DRY_RUN - 安全ガードOK（本番投稿は不可）")
    else:
        print("  注意: 一部の安全ガードが解除されています")
        print("        Phase 3-D/E の手動テスト以外では false に戻してください")

    print()
    print("注意事項:")
    print("  - このチェックは環境変数の存在確認のみです")
    print("  - X API / Threads API への接続は行っていません")
    print("  - READY_FOR_CREDENTIAL_TEST でも本番投稿はできません")
    print("  - 本番投稿には PUBLISH_ENABLED=true + ALLOW_REAL_*_POST=true が別途必要です")
    print("  - Phase 3-D（X 手動1件テスト）まで安全ガードを維持してください")
    print("=" * 60)

    # 安全ガードが解除されている場合のみ警告で終了（FAIL ではない）
    if not guards_safe:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
