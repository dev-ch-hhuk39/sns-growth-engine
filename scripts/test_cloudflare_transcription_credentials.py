"""
test_cloudflare_transcription_credentials.py - Cloudflare 文字起こし認証情報確認（Phase 2.27）

このスクリプトは .env の認証情報が設定されているかをチェックする。
実API 呼び出しは行わない。

確認項目:
  - CLOUDFLARE_ACCOUNT_ID
  - CLOUDFLARE_API_TOKEN
  - ALLOW_TRANSCRIPTION_API

使い方:
  python scripts/test_cloudflare_transcription_credentials.py
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

REQUIRED_VARS = [
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
]

SAFETY_VARS = {
    "ALLOW_TRANSCRIPTION_API": "false",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Cloudflare transcription credential presence check")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when optional Cloudflare credentials are unavailable",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Cloudflare 文字起こし認証情報確認")
    print("=" * 60)
    print("[INFO] 実API呼び出しは行いません\n")

    issues = 0

    # 必須変数チェック
    print("--- 必須環境変数 ---")
    for var in REQUIRED_VARS:
        val = os.environ.get(var, "")
        if val:
            print(f"  [OK]    {var}: set (value hidden)")
        else:
            print(f"  [MISS]  {var}: 未設定")
            issues += 1

    # 安全ガード変数チェック
    print("\n--- 安全ガード変数 ---")
    for var, expected_safe in SAFETY_VARS.items():
        val = os.environ.get(var, expected_safe).lower()
        if val == "true":
            print(f"  [WARN]  {var}={val} (実API が有効になっています)")
        else:
            print(f"  [OK]    {var}={val} (実API は無効)")

    # .env ファイル存在チェック
    print("\n--- .env ファイル ---")
    env_path = os.path.join(_V2_ROOT, ".env")
    if os.path.isfile(env_path):
        print(f"  [OK]    .env ファイルが存在します: {env_path}")
    else:
        print(f"  [WARN]  .env ファイルが見つかりません: {env_path}")
        print(f"         .env.template を参考に作成してください")

    print("\n" + "=" * 60)
    if issues == 0:
        print("  認証情報チェック: OK")
        print("  次のステップ: test_cloudflare_transcription_smoke.py")
    else:
        print(f"  認証情報チェック: UNAVAILABLE ({issues} 件未設定)")
        print("  任意providerは無効です。実APIは呼び出していません。")
        print("  参考: docs/cloudflare-transcription-setup.md")

    return 0 if issues == 0 or not args.strict else 1


if __name__ == "__main__":
    sys.exit(main())
