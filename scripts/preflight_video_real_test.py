"""
preflight_video_real_test.py - 実動画テスト前提条件チェック（Phase 2.30）

実ダウンロード / 音声抽出 / 文字起こしを実行する前に必要な
環境・ツール・環境変数が揃っているかを確認する。

チェック項目:
  1. Python 環境 / パスチェック
  2. yt-dlp のインストール確認
  3. ffmpeg のインストール確認
  4. 環境変数の存在確認（値は出力しない）
  5. downloads/ ディレクトリの書き込み権限確認
  6. ALLOW_* フラグの現在値（実行禁止ガード確認）

使い方:
  python scripts/preflight_video_real_test.py
  python scripts/preflight_video_real_test.py --strict

禁止事項:
  - シークレット値の出力
  - 実API呼び出し
  - 実ダウンロード実行
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass


RESULTS: list[tuple[str, str, str]] = []


def _add(level: str, label: str, msg: str) -> None:
    RESULTS.append((level, label, msg))
    icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}[level]
    print(f"  {icon} {label}: {msg}")


def check_python() -> None:
    ver = sys.version_info
    _add("INFO", "Python", f"{ver.major}.{ver.minor}.{ver.micro}")
    if ver < (3, 9):
        _add("WARN", "Python version", "3.9 以上を推奨します")
    else:
        _add("PASS", "Python version", "3.9+")


def check_yt_dlp() -> None:
    path = shutil.which("yt-dlp")
    if path:
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            ver = result.stdout.strip()
            _add("PASS", "yt-dlp", f"found: {path} (version: {ver})")
        except Exception as e:
            _add("WARN", "yt-dlp", f"found but version check failed: {e}")
    else:
        try:
            import yt_dlp  # type: ignore[import]
            _add("PASS", "yt-dlp (python module)", f"module available: {yt_dlp.__version__}")
        except ImportError:
            _add("FAIL", "yt-dlp", "not found. pip install yt-dlp でインストールしてください")


def check_ffmpeg() -> None:
    path = shutil.which("ffmpeg")
    if path:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, text=True, timeout=5,
            )
            first_line = result.stdout.splitlines()[0] if result.stdout else "?"
            _add("PASS", "ffmpeg", f"found: {path} ({first_line[:60]})")
        except Exception as e:
            _add("WARN", "ffmpeg", f"found but check failed: {e}")
    else:
        _add("FAIL", "ffmpeg", "not found. brew install ffmpeg でインストールしてください")


def check_env_vars() -> None:
    """環境変数の存在確認（値は出力しない）。"""
    required_for_transcription = [
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
    ]
    optional_guards = [
        "ALLOW_TRANSCRIPTION_API",
        "ALLOW_CLOUDINARY_UPLOAD",
        "PUBLISH_ENABLED",
        "ALLOW_REAL_X_POST",
        "ALLOW_REAL_THREADS_POST",
    ]

    for key in required_for_transcription:
        val = os.environ.get(key, "")
        if val:
            _add("PASS", f"env: {key}", "SET (値は非表示)")
        else:
            _add("WARN", f"env: {key}", "未設定（文字起こし実行に必要）")

    for key in optional_guards:
        val = os.environ.get(key, "false").lower()
        if val == "true":
            _add("WARN", f"env: {key}", f"true → 実API/実行が有効になっています（意図的かを確認）")
        else:
            _add("PASS", f"env: {key}", f"false（実行ガード有効）")


def check_downloads_dir() -> None:
    downloads_dir = os.path.join(_V2_ROOT, "downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    test_file = os.path.join(downloads_dir, ".preflight_write_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        _add("PASS", "downloads/ 書き込み権限", f"{downloads_dir}")
    except Exception as e:
        _add("FAIL", "downloads/ 書き込み権限", f"書き込み不可: {e}")


def check_exports_dir() -> None:
    exports_dir = os.path.join(_V2_ROOT, "exports", "hermes")
    os.makedirs(exports_dir, exist_ok=True)

    test_file = os.path.join(exports_dir, ".preflight_write_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        _add("PASS", "exports/hermes/ 書き込み権限", f"{exports_dir}")
    except Exception as e:
        _add("FAIL", "exports/hermes/ 書き込み権限", f"書き込み不可: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="実動画テスト前提条件チェック")
    parser.add_argument("--strict", action="store_true", help="WARN でも非ゼロ終了")
    args = parser.parse_args()

    print("=" * 60)
    print("  preflight_video_real_test.py - 実動画テスト前提条件チェック")
    print("=" * 60)
    print("[INFO] このスクリプトは実ダウンロード・実API呼び出しを一切行いません\n")

    check_python()
    print()
    check_yt_dlp()
    check_ffmpeg()
    print()
    check_env_vars()
    print()
    check_downloads_dir()
    check_exports_dir()

    # サマリー
    pass_count = sum(1 for level, _, _ in RESULTS if level == "PASS")
    warn_count = sum(1 for level, _, _ in RESULTS if level == "WARN")
    fail_count = sum(1 for level, _, _ in RESULTS if level == "FAIL")

    print("\n" + "=" * 60)
    print(f"  [PASS]: {pass_count}  [WARN]: {warn_count}  [FAIL]: {fail_count}")
    print("=" * 60)

    if fail_count > 0:
        print("\n[RESULT] FAIL: 必須項目が揃っていません。上記を確認してください。")
        sys.exit(1)
    elif warn_count > 0 and args.strict:
        print("\n[RESULT] WARN（--strict 指定）")
        sys.exit(1)
    elif warn_count > 0:
        print("\n[RESULT] WARN: 一部項目を確認してください（実行は可能）。")
        sys.exit(0)
    else:
        print("\n[RESULT] PASS: 全前提条件が揃っています。")
        sys.exit(0)


if __name__ == "__main__":
    main()
