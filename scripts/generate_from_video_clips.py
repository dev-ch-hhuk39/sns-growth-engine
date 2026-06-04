"""
generate_from_video_clips.py - クリップ候補から投稿文を生成する（Phase 2.24）

安全ガード:
  - --use-sheets なし: MockSheetsClient で動作
  - --test-write なし: Sheets 書き込みを行わない
  - --mock-llm なし: 実Gemini API を呼び出す（デフォルト: mock）
  - 全投稿は WAITING_REVIEW 状態（READY 昇格は人間レビュー後のみ）
  - 権利ゲート: rights_status=unknown/not_allowed は queue に追加しない
  - media_reuse_risk=high も queue に追加しない

使用方法:
  # モック動作（デフォルト）
  python scripts/generate_from_video_clips.py --account-id night_scout

  # 実Sheets 読み込み + 書き込みなし（確認）
  python scripts/generate_from_video_clips.py --account-id night_scout --use-sheets

  # 実Sheets 接続 + mock LLM + 書き込みあり（test-write）
  python scripts/generate_from_video_clips.py --account-id night_scout --use-sheets --test-write --mock-llm

  # 実Sheets 接続 + 実LLM + 書き込みあり
  python scripts/generate_from_video_clips.py --account-id night_scout --use-sheets --test-write
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
from generation.video_clip_generator import generate_from_clips_batch


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="クリップ候補から投稿文生成（Phase 2.24）")
    p.add_argument("--account-id", required=True,
                   help="アカウントID（night_scout / liver_manager）")
    p.add_argument("--use-sheets", action="store_true",
                   help="実Google Sheets に接続する（なし: MockSheetsClient）")
    p.add_argument("--test-write", action="store_true",
                   help="Sheets 書き込みを有効にする（なし: 読み取り専用）")
    p.add_argument("--mock-llm", action="store_true",
                   help="LLM をモック化する（固定サンプルを返す）")
    p.add_argument("--limit", type=int, default=5,
                   help="処理するクリップ候補の最大件数（デフォルト: 5）")
    p.add_argument("--clip-status", default="candidate",
                   help="対象クリップのステータス（デフォルト: candidate）")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = get_config_partial()

    dry_run = not args.test_write
    force_mock = not args.use_sheets

    mock_llm = args.mock_llm or os.environ.get("MOCK_LLM", "false").lower() in ("1", "true")

    client = make_client(cfg, dry_run=dry_run, force_mock=force_mock)

    print(
        f"[generate_from_video_clips] account={args.account_id} "
        f"use-sheets={args.use_sheets} test-write={args.test_write} "
        f"mock-llm={mock_llm}"
    )

    # アカウント情報取得
    account = client.get_account(args.account_id)
    if not account:
        print(f"[ERROR] アカウントが見つかりません: {args.account_id!r}")
        return 1

    # 対象クリップ候補を取得（text_generation_status=pending のもの）
    candidates = client.get_video_clip_candidates(
        account_id=args.account_id,
        clip_status=args.clip_status,
        limit=args.limit,
    )
    # text_generation_status=pending のもののみ処理
    candidates = [
        c for c in candidates
        if str(c.get("text_generation_status", "pending")).lower() == "pending"
    ]

    if not candidates:
        print(
            f"[generate_from_video_clips] 対象のクリップ候補がありません "
            f"(account_id={args.account_id!r} clip_status={args.clip_status!r} "
            f"text_generation_status=pending)"
        )
        return 0

    print(f"[generate_from_video_clips] 対象クリップ候補: {len(candidates)} 件")

    # 一括生成・保存
    stats = generate_from_clips_batch(
        candidates,
        client,
        account,
        mock_llm=mock_llm,
        dry_run=dry_run,
    )

    print(
        f"[generate_from_video_clips] 完了: "
        f"total={stats['total']} generated={stats['generated']} "
        f"rights_blocked={stats['rights_blocked']} errors={stats['errors']}"
    )
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
