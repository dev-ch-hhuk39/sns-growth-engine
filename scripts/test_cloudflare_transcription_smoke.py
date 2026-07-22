"""
test_cloudflare_transcription_smoke.py - Cloudflare 文字起こし API スモークテスト（Phase 2.27）

このスクリプトは最小限の音声ファイルで実 API を呼び出す。

安全ガード:
  - ALLOW_TRANSCRIPTION_API=true が必要
  - --use-api --confirm-api の両フラグが必要
  - タイムアウト: 30秒
  - テスト用音声は最大5秒

使い方:
  # 認証情報チェックのみ（API 呼び出しなし）
  python scripts/test_cloudflare_transcription_smoke.py

  # 実 API スモークテスト（両フラグ + 環境変数が必要）
  # ALLOW_TRANSCRIPTION_API=true python scripts/test_cloudflare_transcription_smoke.py \\
  #   --use-api --confirm-api

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

from config_loader import get_transcription_config


def _check_env() -> tuple[bool, list[str]]:
    """環境変数を確認して (ok, issues) を返す。"""
    issues: list[str] = []
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        issues.append("CLOUDFLARE_ACCOUNT_ID が未設定")
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        issues.append("CLOUDFLARE_API_TOKEN が未設定")
    return len(issues) == 0, issues


def _run_smoke_test(*, timeout_sec: int = 30) -> dict:
    """実 API を呼び出してスモークテストを実行する。"""
    from transcription.cloudflare_whisper_client import CloudflareWhisperClient

    transcription_cfg = get_transcription_config()
    if not transcription_cfg.get("allow_transcription_api", False):
        return {
            "success": False,
            "error": "ALLOW_TRANSCRIPTION_API=false のため API 呼び出し不可",
        }

    # テスト用の短い音声 URL（実際のテストでは short_audio_url を設定）
    test_audio_url = os.environ.get("CF_SMOKE_TEST_AUDIO_URL", "")
    if not test_audio_url:
        return {
            "success": False,
            "error": "CF_SMOKE_TEST_AUDIO_URL が未設定。テスト用音声 URL を .env に設定してください",
        }

    whisper = CloudflareWhisperClient.from_config(transcription_cfg, dry_run=False)

    import signal

    def _timeout_handler(signum, frame):
        raise TimeoutError(f"スモークテストがタイムアウトしました（{timeout_sec}秒）")

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_sec)

    try:
        result = whisper.transcribe(
            audio_path=test_audio_url,
            reference_post_id="smoke-test-001",
            transcript_id="smoke-tr-001",
            duration_seconds=5.0,
        )
        signal.alarm(0)
        return {
            "success": result.status in ("done", "mock_done"),
            "status": result.status,
            "transcript_length": len(result.transcript_text or ""),
        }
    except TimeoutError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        signal.alarm(0)
        return {"success": False, "error": f"API エラー: {e}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Cloudflare 文字起こし API スモークテスト（Phase 2.27）")
    parser.add_argument("--use-api", action="store_true",
                        help="実 API を呼び出す意思表示")
    parser.add_argument("--confirm-api", action="store_true",
                        help="実 API 呼び出し確認（--use-api と併用必須）")
    args = parser.parse_args()

    print("=" * 60)
    print("  Cloudflare 文字起こし API スモークテスト")
    print("=" * 60)

    # 環境変数チェック
    env_ok, env_issues = _check_env()
    print("\n--- 環境変数チェック ---")
    if env_ok:
        print("  [OK] 必須変数が設定されています")
    else:
        for issue in env_issues:
            print(f"  [MISS] {issue}")

    transcription_cfg = get_transcription_config()
    allow_api = transcription_cfg.get("allow_transcription_api", False)
    print(f"  ALLOW_TRANSCRIPTION_API: {allow_api}")

    # 実 API 呼び出し
    if args.use_api and args.confirm_api:
        if not allow_api:
            print("\n[ERROR] ALLOW_TRANSCRIPTION_API=false のため実API呼び出し不可")
            print("  .env に ALLOW_TRANSCRIPTION_API=true を設定してください")
            return 1
        if not env_ok:
            print("\n[ERROR] 必須環境変数が不足しています")
            return 1

        print("\n--- API スモークテスト実行 ---")
        print("[WARN] 実 Cloudflare API を呼び出します（30秒タイムアウト）")
        result = _run_smoke_test(timeout_sec=30)
        if result.get("success"):
            print(f"  [OK] スモークテスト成功")
            print(f"       status={result.get('status')!r}")
            print(f"       transcript_length={result.get('transcript_length', 0)} chars")
            return 0
        else:
            print(f"  [FAIL] スモークテスト失敗: {result.get('error', '不明')}")
            return 1
    else:
        if args.use_api and not args.confirm_api:
            print("\n[INFO] --confirm-api が未指定のため実API呼び出しをスキップします")
        else:
            print("\n[INFO] 認証情報確認のみ（実API呼び出しなし）")
            print("       実行するには --use-api --confirm-api + ALLOW_TRANSCRIPTION_API=true が必要です")
            print("       詳細: docs/cloudflare-transcription-smoke-test.md")

    if not env_ok:
        print("\n[RESULT] UNAVAILABLE: optional Cloudflare credentials are not configured; no API call was made")
    else:
        print("\n[RESULT] PASS: credentials are available; no API call was made")
    # Missing optional-provider credentials are not a CI failure. Explicit
    # --use-api --confirm-api above remains strict and fails closed.
    return 0


if __name__ == "__main__":
    sys.exit(main())
