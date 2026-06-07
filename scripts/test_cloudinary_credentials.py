"""
test_cloudinary_credentials.py - Cloudinary 認証情報確認（Phase 2.32）

実際のアップロードは行わない。以下を確認する:
  1. 必須認証情報3項目が .env に設定されているか
  2. ALLOW_CLOUDINARY_UPLOAD=false の確認（安全ガード）
  3. .env ファイルの存在確認

使い方:
  python scripts/test_cloudinary_credentials.py
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

REQUIRED_VARS = [
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
]

SAFETY_VARS = {
    "ALLOW_CLOUDINARY_UPLOAD": "false",
}


def main() -> int:
    print("=" * 60)
    print("  test_cloudinary_credentials.py - Cloudinary 認証情報確認（Phase 2.32）")
    print("=" * 60)
    print("[INFO] 実アップロードは行いません（設定確認のみ）\n")

    issues = 0

    # ---- 必須変数チェック ----
    print("--- 必須環境変数（値は表示しません） ---")
    set_count = 0
    missing = []
    for var in REQUIRED_VARS:
        val = os.environ.get(var, "")
        if val:
            print(f"  [set]     {var}")
            set_count += 1
        else:
            print(f"  [missing] {var}")
            missing.append(var)
            issues += 1

    # ---- 安全ガード変数チェック ----
    print("\n--- 安全ガード変数 ---")
    for var, expected_safe in SAFETY_VARS.items():
        val = os.environ.get(var, expected_safe).lower()
        if val == "true":
            print(
                f"  [WARN]  {var}=true\n"
                f"          → 実アップロードが有効になっています\n"
                f"          → テスト以外では false に戻してください"
            )
        else:
            print(f"  [OK]    {var}=false（実アップロード無効）")

    # ---- .env ファイル確認 ----
    print("\n--- .env ファイル ---")
    env_path = os.path.join(_V2_ROOT, ".env")
    if os.path.isfile(env_path):
        print(f"  [OK]    .env が存在します: {env_path}")
    else:
        print(f"  [WARN]  .env が見つかりません: {env_path}")
        print(f"         .env.template を参考に作成してください")

    # ---- 結果サマリー ----
    print("\n" + "=" * 60)
    if issues == 0:
        print(f"  Cloudinary 認証情報チェック: OK（{set_count}/{len(REQUIRED_VARS)} 設定済み）")
        print("  次のステップ: python scripts/test_cloudinary_upload_smoke.py")
    else:
        print(f"  [WARN] 未設定の変数があります: {missing}")
        print("  .env に以下を設定してください:")
        for v in missing:
            print(f"    {v}=<your_value>")
        print("\n  Cloudinary へのサインアップ: https://cloudinary.com/")
        print("  ダッシュボード → Account Details で Cloud name / API Key / API Secret を確認")
    print("=" * 60)

    return issues


if __name__ == "__main__":
    sys.exit(main())
