"""
analyze_video_clips.py - 文字起こしからクリップ候補を抽出して保存する（Phase 2.21）

安全ガード:
  - --use-sheets なし: MockSheetsClient で動作
  - --test-write なし: Sheets 書き込みを行わない
  - --mock-llm なし: 実Gemini API を呼び出す（デフォルト: mock）
  - MOCK_LLM=true / DRY_RUN=true 環境変数でも mock 動作

使用方法:
  # モック動作（デフォルト）
  python scripts/analyze_video_clips.py --account-id night_scout

  # 実Sheets 読み込み + 書き込みなし（確認）
  python scripts/analyze_video_clips.py --account-id night_scout --use-sheets

  # 実Sheets 接続 + mock LLM + 書き込みあり（test-write）
  python scripts/analyze_video_clips.py --account-id night_scout --use-sheets --test-write --mock-llm

  # 実Sheets 接続 + 実LLM + 書き込みあり
  python scripts/analyze_video_clips.py --account-id night_scout --use-sheets --test-write
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
from video.clip_candidate_analyzer import analyze_transcripts_batch, save_clip_candidates


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="クリップ候補分析（Phase 2.21）")
    p.add_argument("--account-id", required=True,
                   help="アカウントID（night_scout / liver_manager）")
    p.add_argument("--use-sheets", action="store_true",
                   help="実Google Sheets に接続する（なし: MockSheetsClient）")
    p.add_argument("--test-write", action="store_true",
                   help="Sheets 書き込みを有効にする（なし: 読み取り専用）")
    p.add_argument("--mock-llm", action="store_true",
                   help="LLM をモック化する（固定サンプルを返す）")
    p.add_argument("--limit", type=int, default=5,
                   help="処理する文字起こしの最大件数（デフォルト: 5）")
    p.add_argument("--n-candidates", type=int, default=6,
                   help="1動画あたりのクリップ候補数（デフォルト: 6）")
    p.add_argument("--transcript-status", default="done",
                   help="対象の文字起こしステータス（デフォルト: done）")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = get_config_partial()

    dry_run = not args.test_write
    force_mock = not args.use_sheets

    # 環境変数でも mock 制御可能
    mock_llm = args.mock_llm or os.environ.get("MOCK_LLM", "false").lower() in ("1", "true")

    client = make_client(cfg, dry_run=dry_run, force_mock=force_mock)

    print(
        f"[analyze_video_clips] account={args.account_id} "
        f"use-sheets={args.use_sheets} test-write={args.test_write} "
        f"mock-llm={mock_llm}"
    )

    # 対象文字起こしを取得
    transcripts = client.get_video_transcripts(
        account_id=args.account_id,
        transcription_status=args.transcript_status,
        limit=args.limit,
    )

    if not transcripts:
        print(
            f"[analyze_video_clips] 対象の文字起こしがありません "
            f"(account_id={args.account_id!r} status={args.transcript_status!r})"
        )
        return 0

    print(f"[analyze_video_clips] 対象文字起こし: {len(transcripts)} 件")

    # クリップ候補を生成
    candidates = analyze_transcripts_batch(
        transcripts,
        args.account_id,
        n_candidates=args.n_candidates,
        mock_llm=mock_llm,
    )

    print(f"[analyze_video_clips] 候補生成合計: {len(candidates)} 件")

    # 保存
    stats = save_clip_candidates(client, candidates, dry_run=dry_run)

    print(
        f"[analyze_video_clips] 完了: "
        f"added={stats['added']} skipped={stats['skipped']} errors={stats['errors']}"
    )
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
