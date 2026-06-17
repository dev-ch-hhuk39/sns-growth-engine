#!/usr/bin/env python3
"""review_source_candidates.py — ソース候補一覧レビュー

使い方:
  python3 scripts/review_source_candidates.py \
    --source-file config/source_accounts/production_sources.example.json \
    [--account night_scout] \
    [--platform x] \
    [--status candidate]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _load_sources(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [s for s in data.get("sources", []) if "source_id" in s]


def _format_row(s: dict) -> str:
    sid = s.get("source_id", "?")
    platform = s.get("source_platform", "?")
    status = s.get("candidate_status", "?")
    fetch = "fetch_ON" if s.get("fetch_enabled") else "fetch_OFF"
    active = "ACTIVE" if s.get("active") else "inactive"
    accounts = ",".join(s.get("target_account_ids", []))
    url = s.get("source_url", "")[:50]
    return f"  {sid:<35} {platform:<10} {status:<15} {fetch:<10} {active:<8} [{accounts}] {url}"


def main() -> int:
    parser = argparse.ArgumentParser(description="ソース候補一覧レビュー")
    parser.add_argument(
        "--source-file",
        default=os.path.join(_ROOT, "config", "source_accounts", "production_sources.example.json"),
    )
    parser.add_argument("--account", default="", help="target_account でフィルタ")
    parser.add_argument("--account-id", default="", help="target_account で絞り込み（互換alias）")
    parser.add_argument("--platform", default="", help="platform でフィルタ")
    parser.add_argument("--status", default="", help="candidate_status でフィルタ")
    parser.add_argument("--show-all", action="store_true", help="disabled も含めて全件表示")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()
    account_filter = args.account or args.account_id

    if not os.path.isfile(args.source_file):
        print(f"[ERROR] ファイルが見つかりません: {args.source_file}")
        return 1

    sources = _load_sources(args.source_file)

    filtered = sources
    if account_filter:
        filtered = [s for s in filtered if account_filter in s.get("target_account_ids", [])]
    if args.platform:
        filtered = [s for s in filtered if s.get("source_platform") == args.platform]
    if args.status:
        filtered = [s for s in filtered if s.get("candidate_status") == args.status]
    if not args.show_all and not args.status:
        filtered = [s for s in filtered if s.get("candidate_status") != "disabled"]

    print(f"\n=== Source Candidates Review ===")
    print(f"  ファイル: {args.source_file}")
    print(f"  フィルタ: account={account_filter or '全て'} platform={args.platform or '全て'} status={args.status or '全て'}")
    print(f"  dry_run: {args.dry_run}")
    print(f"  表示件数: {len(filtered)} / 全体: {len(sources)}")
    print()

    if not filtered:
        print("  (該当ソースなし)")
        return 0

    header = f"  {'source_id':<35} {'platform':<10} {'status':<15} {'fetch':<10} {'active':<8} [accounts] url"
    print(header)
    print("  " + "-" * 100)

    by_account: dict[str, list[dict]] = {}
    for s in filtered:
        for acc in s.get("target_account_ids", ["?"]):
            by_account.setdefault(acc, []).append(s)

    for account, acc_sources in sorted(by_account.items()):
        print(f"\n  --- {account} ({len(acc_sources)} 件) ---")
        for s in acc_sources:
            print(_format_row(s))

    print()

    # サマリ
    statuses: dict[str, int] = {}
    for s in filtered:
        st = s.get("candidate_status", "unknown")
        statuses[st] = statuses.get(st, 0) + 1
    print("  [サマリ] status 内訳:")
    for st, cnt in sorted(statuses.items()):
        print(f"    {st}: {cnt} 件")

    fetch_ready = [s for s in filtered if s.get("fetch_enabled") and not s.get("active")]
    active_count = len([s for s in filtered if s.get("active")])
    print(f"    fetch_enabled=ON (active 前): {len(fetch_ready)} 件")
    print(f"    active=ON: {active_count} 件")

    return 0


if __name__ == "__main__":
    sys.exit(main())
