#!/usr/bin/env python3
"""
plan_generation_jobs.py — 8:2 生成ジョブ計画 CLI（Phase 2.13）

reference_post_scores から参考候補を選択し、
generation_jobs タブへ書き込む（デフォルト dry-run）。

使い方:
  # dry-run（Sheetsへの書き込みなし）
  python3 scripts/plan_generation_jobs.py \\
    --account-id night_scout \\
    --platform x \\
    --dry-run

  # Sheetsへ書き込み
  python3 scripts/plan_generation_jobs.py \\
    --account-id night_scout \\
    --platform x \\
    --no-dry-run \\
    --test-write

  # フィクスチャから読み込んでドライラン
  python3 scripts/plan_generation_jobs.py \\
    --account-id night_scout \\
    --platform x \\
    --input-scores fixtures/sample_reference_post_scores.json \\
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
from generation.generation_planner import (
    plan_generation_jobs,
    plan_daily_counts,
)
from sheets_client import make_client


def main() -> None:
    parser = argparse.ArgumentParser(description="8:2 生成ジョブ計画 CLI")
    parser.add_argument("--account-id", required=True, help="v2 アカウントID")
    parser.add_argument("--platform", default="x", choices=["x", "threads"], help="プラットフォーム")
    parser.add_argument("--daily-target", type=int, default=3, help="1日あたり生成件数")
    parser.add_argument("--ratio", type=float, default=0.8, help="reference_based 比率（デフォルト 0.8）")
    parser.add_argument("--min-score", type=float, default=50.0, help="参考投稿の最低バズスコア")
    parser.add_argument("--auto-approve-threshold", type=float, default=80.0, help="自動承認スコア閾値")
    parser.add_argument("--input-scores", help="スコアJSONファイルパス（省略時はSheetsから取得）")
    parser.add_argument("--use-sheets", action="store_true", help="実SheetsClientを使用")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Sheetsへの書き込みをスキップ（デフォルトON）")
    parser.add_argument("--no-dry-run", action="store_true", help="Sheetsへの書き込みを有効化")
    parser.add_argument("--test-write", action="store_true", help="実Sheetsへ書き込みを実行（--use-sheetsと組み合わせる）")
    args = parser.parse_args()

    dry_run = not args.no_dry_run

    # --- スコアデータ取得 ---
    scores: list[dict] = []
    if args.input_scores:
        with open(args.input_scores, encoding="utf-8") as f:
            scores = json.load(f)
        print(f"[INFO] JSONフィクスチャ読み込み: {len(scores)}件のスコアレコード")
    elif args.use_sheets:
        cfg = get_config_partial()
        client = make_client(cfg, dry_run=False)
        scores = client.get_reference_post_scores(account_id=args.account_id)
        print(f"[INFO] Sheets から reference_post_scores 読み込み: {len(scores)}件")
    else:
        print("[INFO] --input-scores または --use-sheets が未指定のため空スコアで計画します")

    # --- ジョブ計画 ---
    jobs = plan_generation_jobs(
        account_id=args.account_id,
        platform=args.platform,
        scores=scores,
        daily_target_count=args.daily_target,
        ratio=args.ratio,
        min_reference_score=args.min_score,
        auto_approve_threshold=args.auto_approve_threshold,
    )

    ref_count, orig_count = plan_daily_counts(args.daily_target, args.ratio)
    print(f"[INFO] 生成ジョブ: {len(jobs)}件 (ref_based={ref_count}, original={orig_count})")
    for j in jobs:
        ref_id = j.get("reference_post_id", "") or "(none)"
        print(
            f"  job_id={j['job_id'][:8]}... "
            f"mode={j['generation_mode']:<25} "
            f"ref_post={ref_id[:20]!r} "
            f"status={j['status']}"
        )

    # --- Sheets保存 ---
    if args.test_write and not dry_run:
        cfg = get_config_partial()
        write_client = make_client(cfg, dry_run=False)
        result = write_client.save_generation_jobs(jobs)
        print(f"[INFO] save_generation_jobs: saved={result['saved']} skipped={result['skipped']} errors={result['errors']}")
    elif dry_run:
        print(f"[dry-run] {len(jobs)}件の保存をスキップしました（--no-dry-run で有効化）。")
    else:
        print(f"[INFO] 書き込みをスキップしました（--test-write を指定すると保存されます）。")


if __name__ == "__main__":
    main()
