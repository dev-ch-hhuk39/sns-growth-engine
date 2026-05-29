"""
test_x_credentials.py - X API 認証情報の設定確認（Phase 3-D 用）

実際の X API への接続は行わない。以下を確認する:
  1. 必須認証情報4項目が .env に設定されているか
  2. tweepy がインストールされているか
  3. tweepy.Client が初期化できるか（API 呼び出しなし）

投稿は一切行わない。

使い方:
  python scripts/test_x_credentials.py
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_x_credentials


def main() -> None:
    print("=" * 60)
    print("  test_x_credentials.py - X API 認証情報確認")
    print("=" * 60)
    print("[INFO] 投稿は一切行いません（設定確認のみ）")

    creds = get_x_credentials()

    # ---- [1] 必須4項目の確認 ----
    print("\n[1] 認証情報の設定確認（値は表示しません）")
    required = [
        ("X_API_KEY", creds.get("api_key")),
        ("X_API_SECRET", creds.get("api_secret")),
        ("X_ACCESS_TOKEN", creds.get("access_token")),
        ("X_ACCESS_TOKEN_SECRET", creds.get("access_token_secret")),
    ]
    all_set = True
    for key, val in required:
        if val:
            print(f"  [set]     {key}")
        else:
            print(f"  [missing] {key}")
            all_set = False

    if not all_set:
        print("\n[RESULT] NOT_READY: 必須認証情報が不足しています")
        print("  .env に以下を設定してください:")
        print("    X_API_KEY=...")
        print("    X_API_SECRET=...")
        print("    X_ACCESS_TOKEN=...")
        print("    X_ACCESS_TOKEN_SECRET=...")
        print("  取得方法: docs/x-publisher-setup.md を参照")
        sys.exit(1)

    # ---- [2] tweepy インポート確認 ----
    print("\n[2] tweepy インポート確認")
    try:
        import tweepy
        print(f"  [OK] tweepy {tweepy.__version__} インポート成功")
    except ImportError:
        print("  [FAIL] tweepy がインストールされていません")
        print("    pip install tweepy>=4.14.0")
        sys.exit(1)

    # ---- [3] tweepy.Client 初期化確認（API 呼び出しなし）----
    print("\n[3] tweepy.Client 初期化確認（API 呼び出しなし）")
    try:
        client = tweepy.Client(
            consumer_key=creds["api_key"],
            consumer_secret=creds["api_secret"],
            access_token=creds["access_token"],
            access_token_secret=creds["access_token_secret"],
        )
        print("  [OK] tweepy.Client 初期化成功")
        print("  ※ この段階では X API への接続は行いません")
        _ = client  # suppress unused warning
    except Exception as e:
        print(f"  [FAIL] tweepy.Client 初期化失敗: {type(e).__name__}: {e}")
        sys.exit(1)

    # ---- [4] 安全ガード確認 ----
    print("\n[4] 安全ガード確認")
    publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").strip().lower()
    allow_x = os.environ.get("ALLOW_REAL_X_POST", "false").strip().lower()
    is_pe = publish_enabled in ("1", "true", "yes")
    is_ax = allow_x in ("1", "true", "yes")
    print(f"  PUBLISH_ENABLED    : {publish_enabled} ({'有効' if is_pe else '無効'})")
    print(f"  ALLOW_REAL_X_POST  : {allow_x} ({'有効' if is_ax else '無効'})")
    if is_pe and is_ax:
        print("  [INFO] 両ガードが有効です。実投稿が可能な状態です。")
        print("         ※ 実際の投稿前に必ず phase3_safety_check.py を実行してください。")
    else:
        print("  [INFO] 安全ガードが有効（実投稿しない）。Phase 3-D 手動テスト時のみ有効化してください。")

    print("\n" + "=" * 60)
    print("[RESULT] READY_FOR_CREDENTIAL_TEST")
    print("  認証情報が設定済み。tweepy が利用可能。")
    print("  実際の API 疎通テスト前に check_publisher_credentials.py も実行してください。")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
