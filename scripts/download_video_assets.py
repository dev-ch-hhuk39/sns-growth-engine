"""
download_video_assets.py - 動画ダウンロード + 音声抽出 CLI（Phase 2.26）

安全ガード:
  - デフォルト: dry_run（実ダウンロード・音声抽出なし）
  - ダウンロード実行: --download --confirm-download の両方が必要
  - 音声抽出実行: --extract-audio --confirm-extract の両方が必要
  - TikTok は未対応（WARN を出してスキップ）

使い方:
  # dry-run（デフォルト）
  python scripts/download_video_assets.py --account-id night_scout

  # 実Sheets + dry-run確認
  python scripts/download_video_assets.py --account-id night_scout --use-sheets

  # 実ダウンロード（両フラグ必要）
  python scripts/download_video_assets.py --account-id night_scout \\
    --use-sheets --download --confirm-download

  # ダウンロード + 音声抽出
  python scripts/download_video_assets.py --account-id night_scout \\
    --use-sheets --download --confirm-download --extract-audio --confirm-extract
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

from config_loader import get_config_partial
from sheets_client import make_client
from video.video_downloader import download_videos_batch
from video.audio_extractor import extract_audio_batch


def main() -> int:
    parser = argparse.ArgumentParser(description="動画ダウンロード + 音声抽出 CLI（Phase 2.26）")
    parser.add_argument("--account-id", required=True, help="アカウントID")
    parser.add_argument("--use-sheets", action="store_true", help="実Google Sheets 接続")
    parser.add_argument("--test-write", action="store_true", help="Sheets 書き込み有効化")
    parser.add_argument("--download", action="store_true", help="yt-dlp ダウンロードを実行する意思表示")
    parser.add_argument("--confirm-download", action="store_true",
                        help="実ダウンロード確認（--download と併用必須）")
    parser.add_argument("--extract-audio", action="store_true", help="音声抽出を実行する意思表示")
    parser.add_argument("--confirm-extract", action="store_true",
                        help="実音声抽出確認（--extract-audio と併用必須）")
    parser.add_argument("--output-dir-video", default="downloads/videos",
                        help="動画出力ディレクトリ（デフォルト: downloads/videos）")
    parser.add_argument("--output-dir-audio", default="downloads/audio",
                        help="音声出力ディレクトリ（デフォルト: downloads/audio）")
    parser.add_argument("--limit", type=int, default=5, help="処理件数上限（デフォルト: 5）")
    args = parser.parse_args()

    print("=" * 60)
    print("  download_video_assets.py - 動画ダウンロード + 音声抽出")
    print("=" * 60)
    print("[INFO] SNS 本番投稿は行いません")

    dry_run = not args.test_write
    force_mock = not args.use_sheets

    do_download = args.download and args.confirm_download
    do_extract = args.extract_audio and args.confirm_extract

    if args.download and not args.confirm_download:
        print("[WARN] --confirm-download が未指定のため dry-run でダウンロードを確認します")
    if args.extract_audio and not args.confirm_extract:
        print("[WARN] --confirm-extract が未指定のため dry-run で音声抽出を確認します")

    if do_download:
        print("[INFO] 実ダウンロードを実行します（yt-dlp）")
    else:
        print("[INFO] DRY-RUN: ダウンロードは実行しません")

    if do_extract:
        print("[INFO] 実音声抽出を実行します（ffmpeg）")
    else:
        print("[INFO] DRY-RUN: 音声抽出は実行しません")

    cfg = get_config_partial()
    client = make_client(cfg, dry_run=dry_run, force_mock=force_mock)

    # 動画 reference_posts を取得
    try:
        posts = client.get_reference_posts(account_id=args.account_id, status="ACTIVE")
    except Exception:
        posts = []

    video_posts = [
        p for p in posts
        if str(p.get("content_type", "")).lower() == "video"
    ][:args.limit]

    if not video_posts:
        print(f"\n[INFO] 動画参考投稿なし (account_id={args.account_id!r})")
        return 0

    print(f"\n対象: {len(video_posts)} 件")

    # ダウンロード
    download_results = download_videos_batch(
        video_posts,
        output_dir=args.output_dir_video,
        dry_run=not do_download,
        confirm_download=do_download,
    )

    success = [r for r in download_results if r.success]
    failed = [r for r in download_results if not r.success]
    print(f"\nダウンロード: {len(success)} 成功 / {len(failed)} 失敗")
    for r in failed:
        print(f"  [FAIL] {r.reference_post_id}: {r.error}")

    # 音声抽出
    if args.extract_audio and success:
        video_map = [
            {
                "reference_post_id": r.reference_post_id,
                "account_id": args.account_id,
                "local_path": r.local_path,
            }
            for r in success
        ]
        extract_results = extract_audio_batch(
            video_map,
            output_dir=args.output_dir_audio,
            dry_run=not do_extract,
            confirm_extract=do_extract,
        )
        ex_success = [r for r in extract_results if r.success]
        ex_failed = [r for r in extract_results if not r.success]
        print(f"\n音声抽出: {len(ex_success)} 成功 / {len(ex_failed)} 失敗")
        for r in ex_failed:
            print(f"  [FAIL] {r.reference_post_id}: {r.error}")

    print("\n[OK] 完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
