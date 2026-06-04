"""
transcribe_videos.py - 動画文字起こし実行スクリプト

安全ガード:
  - ALLOW_TRANSCRIPTION_API=false（デフォルト）: 実API呼び出し禁止
  - --allow-real-transcription フラグを追加しても ALLOW_TRANSCRIPTION_API=true 必須
  - --use-sheets なし: MockSheetsClient で動作
  - --test-write なし: Sheets 書き込みを行わない

使用方法:
  # モック動作（デフォルト）
  python3 scripts/transcribe_videos.py --account-id night_scout
  # MockSheetsClient + 書き込みあり
  python3 scripts/transcribe_videos.py --account-id night_scout --test-write
  # 実Sheets 接続 + 書き込みなし（読み取り確認）
  python3 scripts/transcribe_videos.py --account-id night_scout --use-sheets
  # 実Sheets 接続 + 書き込みあり
  python3 scripts/transcribe_videos.py --account-id night_scout --use-sheets --test-write
  # 実API（ALLOW_TRANSCRIPTION_API=true 設定後のみ）:
  # python3 scripts/transcribe_videos.py --account-id night_scout --use-sheets --test-write --allow-real-transcription
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from config_loader import get_config_partial, get_transcription_config
from sheets_client import make_client
from transcription.cloudflare_whisper_client import CloudflareWhisperClient
from transcription.transcription_limiter import TranscriptionLimiter
from transcription.transcript_parser import build_clip_candidates_from_transcripts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="動画文字起こし実行")
    p.add_argument("--account-id", required=True, help="アカウントID（night_scout / liver_manager）")
    # 新CLIフラグ標準（--use-sheets / --test-write）
    p.add_argument("--use-sheets", action="store_true",
                   help="実Google Sheets に接続する（なし: MockSheetsClient）")
    p.add_argument("--test-write", action="store_true",
                   help="Sheets 書き込みを有効にする（なし: 読み取り専用）")
    # 後方互換フラグ（非推奨）
    p.add_argument("--dry-run", action="store_true", default=False,
                   help="[非推奨] --test-write なしと同等。後方互換のため残存")
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="[非推奨] 後方互換のため残存")
    p.add_argument("--mock-sheets", action="store_true",
                   help="[非推奨] MockSheetsClient 強制（--use-sheets なしと同等）")
    p.add_argument("--allow-real-transcription", action="store_true",
                   help="実Cloudflare API を呼び出す（ALLOW_TRANSCRIPTION_API=true も必要）")
    p.add_argument("--limit", type=int, default=10,
                   help="処理する動画の最大件数（デフォルト: 10）")
    p.add_argument("--generate-clips", action="store_true",
                   help="文字起こし後にクリップ候補を生成・保存する")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = get_config_partial()
    transcription_cfg = get_transcription_config()

    # 新CLIフラグ標準に合わせてdry_runを決定
    # --test-write があれば書き込み有効、なければdry_run
    # 後方互換: --no-dry-run も dry_run=False として扱う
    dry_run = not args.test_write and not (hasattr(args, "dry_run") and not args.dry_run)
    force_mock = not args.use_sheets or args.mock_sheets

    allow_real = args.allow_real_transcription and transcription_cfg.get("allow_transcription_api", False)

    if args.allow_real_transcription and not transcription_cfg.get("allow_transcription_api", False):
        print("[WARN] --allow-real-transcription が指定されましたが ALLOW_TRANSCRIPTION_API=false のため dry_run で動作します")

    client = make_client(cfg, dry_run=dry_run, force_mock=force_mock)
    whisper = CloudflareWhisperClient.from_config(transcription_cfg, dry_run=not allow_real)
    limiter = TranscriptionLimiter(
        client,
        limit_minutes=float(transcription_cfg.get("daily_limit_minutes", 120)),
        dry_run=dry_run,
    )

    print(f"[transcribe_videos] account={args.account_id} dry_run={dry_run} allow_real={allow_real}")
    print(f"[transcribe_videos] 残り上限: {limiter.remaining_minutes:.1f} 分")

    pending_videos = client.get_reference_posts(
        account_id=args.account_id,
        status="ACTIVE",
    )
    pending_videos = [
        v for v in pending_videos
        if str(v.get("content_type", "")).lower() == "video"
        and str(v.get("transcription_status", "pending")).lower() == "pending"
    ]

    if not pending_videos:
        print("[transcribe_videos] 文字起こし対象の動画がありません（content_type=video, transcription_status=pending）")
        return 0

    pending_videos = pending_videos[: args.limit]
    print(f"[transcribe_videos] 対象動画: {len(pending_videos)} 件")

    results = []
    for video in pending_videos:
        reference_post_id = str(video.get("id", ""))
        video_url = str(video.get("video_url", ""))
        duration_seconds = float(video.get("duration_seconds", 0.0) or 0.0)
        transcript_id = f"tr-{_short_uuid()}"

        if not limiter.can_process(duration_seconds):
            print(f"[SKIP] 上限超過: {reference_post_id!r} duration={duration_seconds:.0f}s")
            limiter.record_skip()
            continue

        print(f"[transcribe] {reference_post_id!r} duration={duration_seconds:.0f}s url={video_url[:60]!r}")
        result = whisper.transcribe(
            audio_path=video_url,
            reference_post_id=reference_post_id,
            transcript_id=transcript_id,
            duration_seconds=duration_seconds,
        )
        limiter.record(duration_seconds=duration_seconds, status=result.status)

        row = result.to_sheets_row()
        row["account_id"] = args.account_id
        row["source_platform"] = str(video.get("platform", ""))
        row["video_url"] = video_url

        if not dry_run:
            client.save_video_transcript(row)
            client.update_reference_post_status(reference_post_id, "ACTIVE")
        else:
            print(f"  [dry-run] save_video_transcript: transcript_id={transcript_id!r} status={result.status!r}")

        results.append(row)

    if args.generate_clips and results:
        done_transcripts = [r for r in results if r.get("transcription_status") == "done"]
        clips = build_clip_candidates_from_transcripts(done_transcripts, account_id=args.account_id)
        print(f"[clips] 候補生成: {len(clips)} 件")
        for clip in clips:
            if not dry_run:
                client.save_video_clip_candidate(clip)
            else:
                print(f"  [dry-run] save_video_clip_candidate: clip_id={clip['clip_id']!r}")

    limiter.flush()
    summary = limiter.summary()
    print(f"[transcribe_videos] 完了: processed={summary['processed_count']} "
          f"skipped={summary['skipped_daily_limit_count']} failed={summary['failed_count']} "
          f"used={summary['used_minutes']:.1f}min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
