"""
test_cloudinary_upload_smoke.py - Cloudinary 小規模アップロードスモークテスト（Phase 2.32）

安全ガード（3重）:
  ALLOW_CLOUDINARY_UPLOAD=true が必要
  --upload フラグが必要
  --confirm-upload フラグが必要

デフォルト動作: dry-run（実アップロードなし）

ファイルサイズ上限: 512KB（テスト用）
許可する拡張子: .jpg .jpeg .png .webp .mp4（5秒以内）

使い方:
  # dry-run 確認（実アップロードなし）
  python scripts/test_cloudinary_upload_smoke.py --file tests/fixtures/sample_image.jpg

  # 実アップロード（3フラグ + 環境変数が必要）
  # ALLOW_CLOUDINARY_UPLOAD=true \\
  #   python scripts/test_cloudinary_upload_smoke.py \\
  #   --file tests/fixtures/sample_image.jpg \\
  #   --upload --confirm-upload

禁止事項:
  - 実アップロード（3重ガードが解除されない限り）
  - シークレット値の表示
  - 大きいファイルのアップロード（512KB超）
  - SNS本番投稿
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

from media.cloudinary_client import upload_to_cloudinary

MAX_FILE_SIZE_BYTES = 512 * 1024  # 512KB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}

RESULTS: list[tuple[str, str, str]] = []


def _add(level: str, label: str, msg: str) -> None:
    RESULTS.append((level, label, msg))
    icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}[level]
    print(f"  {icon} {label}: {msg}")


def check_file(file_path: str) -> bool:
    """ファイルの安全確認。"""
    print("\n--- ファイル確認 ---")
    if not os.path.isfile(file_path):
        _add("FAIL", "ファイル存在確認", f"見つかりません: {file_path}")
        return False

    size = os.path.getsize(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        _add("FAIL", "拡張子確認", f"許可されていない拡張子: {ext!r} (許可: {sorted(ALLOWED_EXTENSIONS)})")
        return False

    _add("PASS", "拡張子確認", f"{ext}")

    if size > MAX_FILE_SIZE_BYTES:
        _add("FAIL", "ファイルサイズ確認", f"{size / 1024:.1f}KB > 上限 {MAX_FILE_SIZE_BYTES // 1024}KB")
        return False

    _add("PASS", "ファイルサイズ確認", f"{size / 1024:.1f}KB ≤ {MAX_FILE_SIZE_BYTES // 1024}KB")
    return True


def check_credentials() -> bool:
    """Cloudinary 認証情報確認（値は表示しない）。"""
    print("\n--- 認証情報確認 ---")
    required = ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]
    all_set = True
    for var in required:
        val = os.environ.get(var, "")
        if val:
            _add("PASS", var, "set（値は非表示）")
        else:
            _add("FAIL", var, "未設定（.env に追加してください）")
            all_set = False
    return all_set


def check_safety_guard() -> bool:
    """安全ガードの確認。"""
    print("\n--- 安全ガード確認 ---")
    allow = os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "false").lower()
    if allow == "true":
        _add("WARN", "ALLOW_CLOUDINARY_UPLOAD", "true（実アップロード有効化フラグ）")
    else:
        _add("PASS", "ALLOW_CLOUDINARY_UPLOAD", f"false（実アップロード無効）")
    return True


def run_smoke_upload(
    file_path: str,
    *,
    dry_run: bool = True,
) -> bool:
    """スモークアップロードを実行（または dry-run）。"""
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    api_key = os.environ.get("CLOUDINARY_API_KEY", "")
    api_secret = os.environ.get("CLOUDINARY_API_SECRET", "")

    if dry_run:
        print(f"\n  [dry-run] アップロード対象ファイル: {file_path}")
        print(f"  [dry-run] CLOUDINARY_CLOUD_NAME: {'set' if cloud_name else 'missing'}")
        print(f"  [dry-run] 実アップロードは --upload --confirm-upload で実行できます")
        print(f"  [dry-run] 事前条件: ALLOW_CLOUDINARY_UPLOAD=true が必要")
        return True

    allow_upload = os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "false").lower() == "true"
    if not allow_upload:
        _add("FAIL", "安全ガード", "ALLOW_CLOUDINARY_UPLOAD=false のため実アップロード不可")
        return False

    try:
        print(f"\n  実アップロード実行中: {file_path}")
        with open(file_path, "rb") as fh:
            file_bytes = fh.read()

        result = upload_to_cloudinary(
            file_bytes=file_bytes,
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            public_id=f"sns_v2_smoke_test/test_{os.path.basename(file_path)}",
            allow_upload=True,
        )
        public_id = result.get("public_id", "?")
        _add("PASS", "アップロード完了", f"public_id={public_id}")
        print("\n  [重要] テスト後の削除手順:")
        print(f"    1. Cloudinary Media Library にアクセス")
        print(f"    2. フォルダ sns_v2_smoke_test を開く")
        print(f"    3. {public_id} を削除する")
        print(f"    4. または: cloudinary API で DELETE リクエストを実行")
        return True
    except Exception as e:
        _add("FAIL", "アップロード失敗", str(e))
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Cloudinary 小規模アップロードスモークテスト")
    parser.add_argument("--file", required=True, help="テスト対象ファイルパス")
    parser.add_argument("--upload", action="store_true", help="実アップロードフラグ（--confirm-upload も必要）")
    parser.add_argument("--confirm-upload", action="store_true", help="実アップロード確認フラグ")
    args = parser.parse_args()

    print("=" * 60)
    print("  test_cloudinary_upload_smoke.py - Cloudinaryスモークテスト（Phase 2.32）")
    print("=" * 60)

    real_upload = args.upload and args.confirm_upload
    if real_upload:
        allow_env = os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "false").lower()
        if allow_env != "true":
            print(f"[ERROR] ALLOW_CLOUDINARY_UPLOAD=false のため実アップロード不可")
            print("  → 実テスト時は環境変数を設定してください（テスト後は false に戻す）")
            sys.exit(1)
        print("[INFO] 実アップロードモード（3重ガード解除済み）")
    else:
        print("[INFO] dry-run モード（実アップロードなし）")
        if args.upload and not args.confirm_upload:
            print("[WARN] --confirm-upload が指定されていないため dry-run で実行します")

    cred_ok = check_credentials()
    file_ok = check_file(args.file)
    check_safety_guard()

    if not cred_ok:
        print("\n[RESULT] FAIL: 認証情報が不足しています")
        print("  → python scripts/test_cloudinary_credentials.py で確認してください")
        sys.exit(1)

    if not file_ok:
        print("\n[RESULT] FAIL: ファイルの確認に失敗しました")
        sys.exit(1)

    ok = run_smoke_upload(args.file, dry_run=not real_upload)

    fail_count = sum(1 for r in RESULTS if r[0] == "FAIL")
    warn_count = sum(1 for r in RESULTS if r[0] == "WARN")

    print("\n" + "=" * 60)
    if fail_count > 0:
        print("[RESULT] FAIL: エラーがあります")
        sys.exit(1)
    elif warn_count > 0:
        print("[RESULT] WARN: 警告があります。確認してください。")
    else:
        if real_upload:
            print("[RESULT] PASS: 実アップロード成功")
            print("[重要] テスト完了後、Cloudinary Media Library からテスト画像を削除してください")
        else:
            print("[RESULT] PASS: dry-run 確認完了")
            print(f"[次のステップ] 実アップロードは以下で実行できます（今回は実行しない）:")
            print(
                f"  ALLOW_CLOUDINARY_UPLOAD=true \\\n"
                f"  python scripts/test_cloudinary_upload_smoke.py \\\n"
                f"  --file {args.file} --upload --confirm-upload"
            )


if __name__ == "__main__":
    main()
