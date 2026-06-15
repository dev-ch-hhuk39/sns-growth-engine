#!/usr/bin/env python3
"""save_pipeline_outputs.py - パイプライン出力保存 CLI"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.storage.pipeline_store import PipelineStore


def main() -> int:
    parser = argparse.ArgumentParser(description="パイプライン出力を保存する")
    parser.add_argument("--run-id", required=True, help="run_id (例: RUN_abc123)")
    parser.add_argument("--stage", default="summary", help="保存ステージ名 (デフォルト: summary)")
    parser.add_argument("--input-json", help="入力 JSON ファイルパス")
    parser.add_argument("--output-dir", default="output/pipeline_runs", help="出力ディレクトリ")
    parser.add_argument("--dry-run", action="store_true", default=True, help="dry-run モード")
    parser.add_argument("--no-dry-run", action="store_true", help="dry-run を無効化（実保存）")
    args = parser.parse_args()

    dry_run = not args.no_dry_run

    store = PipelineStore(output_dir=args.output_dir)

    data: dict = {}
    if args.input_json:
        with open(args.input_json, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"run_id": args.run_id, "stage": args.stage, "note": "no input provided"}

    result = store.save(args.run_id, args.stage, data, dry_run=dry_run)
    print(f"[{'DRY_RUN' if dry_run else 'SAVED'}] {result}")

    existing = store.list_runs()
    print(f"  保存済み run_id 数: {len(existing)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
