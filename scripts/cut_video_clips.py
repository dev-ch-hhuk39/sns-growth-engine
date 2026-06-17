"""
cut_video_clips.py - クリップ候補を ffmpeg で切り抜く（Phase 2.22）

安全ガード:
  - --dry-run（デフォルト: True）: ffmpeg は実行しない
  - 実切り抜きは --cut --confirm-cut の両方が必要
  - --use-sheets なし: MockSheetsClient で動作
  - --test-write なし: Sheets 書き込みを行わない

使用方法:
  # dry-run モック動作（デフォルト）
  python scripts/cut_video_clips.py --account-id night_scout --dry-run

  # 実Sheets 読み込み + dry-run
  python scripts/cut_video_clips.py --account-id night_scout --use-sheets --dry-run

  # 実Sheets 接続 + dry-run + 書き込みあり（test-write）
  python scripts/cut_video_clips.py --account-id night_scout --use-sheets --test-write --dry-run

  # 実切り抜き（両フラグ必要）
  # python scripts/cut_video_clips.py --account-id night_scout --use-sheets --test-write --cut --confirm-cut
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
from video.clip_cutter import cut_clips_batch, update_cut_status


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="クリップ切り抜き（Phase 2.22）")
    p.add_argument("--account-id", required=True,
                   help="アカウントID（night_scout / liver_manager）")
    p.add_argument("--use-sheets", action="store_true",
                   help="実Google Sheets に接続する（なし: MockSheetsClient）")
    p.add_argument("--mock", action="store_true",
                   help="モック/ローカルdry-runとして動作する")
    p.add_argument("--test-write", action="store_true",
                   help="Sheets 書き込みを有効にする（なし: 読み取り専用）")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="ffmpeg を実行しない（デフォルト: True）")
    p.add_argument("--cut", action="store_true",
                   help="実切り抜きを有効化する（--confirm-cut も必要）")
    p.add_argument("--confirm-cut", action="store_true",
                   help="実切り抜き確認フラグ（--cut と併用）")
    p.add_argument("--output-dir", default="clips",
                   help="切り抜きファイルの出力先（デフォルト: clips/）")
    p.add_argument("--limit", type=int, default=5,
                   help="処理するクリップ候補の最大件数（デフォルト: 5）")
    p.add_argument("--clip-status", default="candidate",
                   help="対象クリップのステータス（デフォルト: candidate）")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = get_config_partial()

    dry_run_sheets = not args.test_write
    force_mock = not args.use_sheets

    # 実切り抜きは --cut --confirm-cut 両方必要
    actually_cut = args.cut and args.confirm_cut
    ffmpeg_dry_run = not actually_cut

    if args.cut and not args.confirm_cut:
        print("[BLOCKED] --cut が指定されましたが --confirm-cut がないため切り抜きをブロックします")
        print("  実cutは実行していません")
        return 1

    client = make_client(cfg, dry_run=dry_run_sheets, force_mock=force_mock)

    print(
        f"[cut_video_clips] account={args.account_id} "
        f"use-sheets={args.use_sheets} test-write={args.test_write} "
        f"ffmpeg-dry-run={ffmpeg_dry_run}"
    )

    # 対象クリップ候補を取得
    candidates = client.get_video_clip_candidates(
        account_id=args.account_id,
        clip_status=args.clip_status,
        limit=args.limit,
    )

    if not candidates:
        print(
            f"[cut_video_clips] 対象のクリップ候補がありません "
            f"(account_id={args.account_id!r} status={args.clip_status!r})"
        )
        return 0

    print(f"[cut_video_clips] 対象クリップ候補: {len(candidates)} 件")

    # reference_post_id → source video path のマッピング（実環境では別途提供）
    source_video_map: dict[str, str] = {}

    results = cut_clips_batch(
        candidates,
        source_video_map,
        output_dir=args.output_dir,
        dry_run=ffmpeg_dry_run,
        confirm_cut=args.confirm_cut,
    )

    success = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    print(f"[cut_video_clips] 切り抜き結果: success={success} failed={failed}")

    # Sheets に cut_status を更新
    stats = update_cut_status(client, results, dry_run=dry_run_sheets)
    print(
        f"[cut_video_clips] 完了: "
        f"updated={stats['updated']} skipped={stats['skipped']} errors={stats['errors']}"
    )
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
