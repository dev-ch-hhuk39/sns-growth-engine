#!/usr/bin/env python3
"""
generate_from_jobs.py — generation_jobs から投稿文を生成する CLI（Phase 2.14）

generation_jobs タブの pending ジョブに対してGemini APIを呼び出し、
生成した投稿文を drafts タブに保存する。

安全ガード:
  --mock-llm  (デフォルト ON): 実際のGemini APIを呼び出さない
  --dry-run   (デフォルト ON): Sheetsへの書き込みをスキップ

使い方:
  # モック生成 dry-run
  python3 scripts/generate_from_jobs.py \\
    --account-id night_scout \\
    --mock-llm \\
    --dry-run

  # Sheetsのジョブを使ってモック生成（Sheetsへの書き込みあり）
  python3 scripts/generate_from_jobs.py \\
    --account-id night_scout \\
    --use-sheets \\
    --mock-llm \\
    --no-dry-run

  # フィクスチャのジョブで生成（dry-run）
  python3 scripts/generate_from_jobs.py \\
    --account-id night_scout \\
    --input-jobs fixtures/sample_generation_jobs.json \\
    --input-scores fixtures/sample_x_post_scores.json \\
    --mock-llm \\
    --dry-run
"""
from __future__ import annotations

import argparse
import json
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
from generation.reference_based_generator import execute_generation_jobs
from sheets_client import make_client


def main() -> None:
    parser = argparse.ArgumentParser(description="generation_jobs から投稿文を生成する CLI")
    parser.add_argument("--account-id", required=True, help="v2 アカウントID")
    parser.add_argument("--input-jobs", help="ジョブJSONファイルパス")
    parser.add_argument("--input-scores", help="スコアJSONファイルパス")
    parser.add_argument("--use-sheets", action="store_true", help="実SheetsClientを使用")
    parser.add_argument("--limit", type=int, help="処理件数上限")
    parser.add_argument("--mock-llm", action="store_true", default=True, help="LLM呼び出しをモックにする（デフォルトON）")
    parser.add_argument("--no-mock-llm", action="store_true", help="LLM呼び出しを実際に行う（GEMINI_API_KEY必要）")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Sheetsへの書き込みをスキップ（デフォルトON）")
    parser.add_argument("--no-dry-run", action="store_true", help="Sheetsへの書き込みを有効化")
    args = parser.parse_args()

    dry_run = not args.no_dry_run
    mock_llm = not args.no_mock_llm

    if mock_llm:
        os.environ["MOCK_LLM"] = "true"
        print("[INFO] MOCK_LLM=true — 実際のGemini API呼び出しをスキップします")
    else:
        print("[INFO] MOCK_LLM=false — 実際のGemini API呼び出しを行います")

    # --- ジョブデータ取得 ---
    jobs: list[dict] = []
    scores: list[dict] = []

    if args.input_jobs:
        with open(args.input_jobs, encoding="utf-8") as f:
            jobs = json.load(f)
        print(f"[INFO] ジョブJSON読み込み: {len(jobs)}件")
    elif args.use_sheets:
        cfg = get_config_partial()
        client = make_client(cfg, dry_run=False)
        jobs = client.get_generation_jobs(account_id=args.account_id, status="pending")
        print(f"[INFO] Sheets から pending ジョブ読み込み: {len(jobs)}件")
    else:
        print("[ERROR] --input-jobs または --use-sheets を指定してください。")
        sys.exit(1)

    if args.input_scores:
        with open(args.input_scores, encoding="utf-8") as f:
            scores = json.load(f)
        print(f"[INFO] スコアJSON読み込み: {len(scores)}件")
    elif args.use_sheets:
        cfg = get_config_partial()
        client = make_client(cfg, dry_run=False)
        scores = client.get_reference_post_scores(account_id=args.account_id)
        print(f"[INFO] Sheets から reference_post_scores 読み込み: {len(scores)}件")

    if args.limit:
        jobs = jobs[:args.limit]

    if not jobs:
        print("[INFO] 処理するジョブがありません。終了します。")
        return

    # --- アカウント情報取得 ---
    account: dict = {"account_id": args.account_id}
    if args.use_sheets and not dry_run:
        cfg = get_config_partial()
        ac = make_client(cfg, dry_run=False).get_account(args.account_id)
        if ac:
            account = ac
    else:
        try:
            from sheets_client import MockSheetsClient
            mock = MockSheetsClient()
            ac = mock.get_account(args.account_id)
            if ac:
                account = ac
        except Exception:
            pass

    # --- 投稿生成 ---
    if dry_run:
        write_client = make_client({}, dry_run=True, force_mock=True)
    else:
        cfg = get_config_partial()
        write_client = make_client(cfg, dry_run=False)

    results = execute_generation_jobs(
        jobs=jobs,
        scores=scores,
        account=account,
        client=write_client,
        dry_run=dry_run,
    )

    # --- 結果表示 ---
    done = sum(1 for r in results if r["status"] != "FAILED")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    waiting = sum(1 for r in results if r["status"] == "WAITING_REVIEW")

    print(f"\n[INFO] 生成完了: {done}件成功 / {failed}件失敗 / {waiting}件WAITING_REVIEW")
    for r in results:
        print(
            f"  job={r['job_id'][:8]}... "
            f"mode={r['generation_mode']:<25} "
            f"status={r['status']:<15} "
            f"policy={r['text_policy_status']}"
        )


if __name__ == "__main__":
    main()
