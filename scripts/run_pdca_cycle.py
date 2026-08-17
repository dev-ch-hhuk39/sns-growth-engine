"""
run_pdca_cycle.py - PDCAオーケストレーター CLI（Phase 7.E）

posted_results → 分析 → improvement_suggestions → 次回generation_jobs候補。
実投稿なし。自動反映なし。learning_rules auto active 禁止。

使い方:
  python scripts/run_pdca_cycle.py --account-id night_scout --platform x --days 7 --dry-run --mock --generate-next-plan
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

from learning.pdca_orchestrator import PDCAOrchestrator  # noqa: E402
from metrics_pdca_contract import measured_results_only, pdca_input_summary  # noqa: E402


# サンプルposted_results（mock用）
_MOCK_RESULTS = [
    {
        "result_id": "pr_001", "account_id": "night_scout", "platform": "x",
        "content_type": "single_post", "generation_mode": "single_post",
        "likes": 80, "reposts": 15, "replies": 5, "impressions": 2000,
        "posted_at": "2026-06-10T09:00:00Z",
    },
    {
        "result_id": "pr_002", "account_id": "night_scout", "platform": "x",
        "content_type": "thread_series", "generation_mode": "thread_series",
        "series_id": "ts_night_scout_x_abc123", "post_index": 0, "post_role": "hook",
        "likes": 120, "reposts": 30, "replies": 8, "impressions": 2500,
        "posted_at": "2026-06-11T09:00:00Z",
    },
    {
        "result_id": "pr_003", "account_id": "night_scout", "platform": "x",
        "content_type": "thread_series", "generation_mode": "thread_series",
        "series_id": "ts_night_scout_x_abc123", "post_index": 1, "post_role": "context",
        "likes": 32, "reposts": 8, "replies": 2, "impressions": 800,
        "posted_at": "2026-06-11T09:05:00Z",
    },
    {
        "result_id": "pr_004", "account_id": "night_scout", "platform": "x",
        "content_type": "reference_based", "generation_mode": "reference_based",
        "likes": 55, "reposts": 10, "replies": 3, "impressions": 1500,
        "posted_at": "2026-06-12T09:00:00Z",
    },
]


def load_measured_results_from_sheets(account_id: str, platform: str) -> list[dict]:
    """Read production results without mutation; never substitute synthetic metrics."""
    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
    rows = [dict(row) for row in client._ws("posted_results").get_all_records()]
    return measured_results_only(rows, account_id=account_id, platform=platform)


def main() -> None:
    parser = argparse.ArgumentParser(description="PDCAオーケストレーター CLI")
    parser.add_argument("--account-id", default="night_scout")
    parser.add_argument("--platform", default="x", choices=["x", "threads"])
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="required together with --apply --confirm-pdca for a PDCA audit write")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--test-write", action="store_true")
    parser.add_argument("--apply", action="store_true", help="write PDCA audit row (requires --confirm-pdca)")
    parser.add_argument("--confirm-pdca", action="store_true", help="explicit confirmation for PDCA audit write")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--generate-next-plan", action="store_true")
    parser.add_argument("--max-suggestions", type=int, default=5)
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    account_id = args.account_id
    platform = args.platform

    print(f"\n=== run_pdca_cycle: {account_id} / {platform} ===")
    print(f"  days             : {args.days}")
    print(f"  dry_run          : {args.dry_run}")
    print(f"  mock             : {args.mock}")
    print(f"  generate_next    : {args.generate_next_plan}")
    print(f"  max_suggestions  : {args.max_suggestions}")

    # draft_only でも同一accountのMEASURED実績は読み取れる。自動適用はしない。
    try:
        from accounts.account_config import load_account_config
        acct_cfg = load_account_config(account_id)
        if acct_cfg.is_draft_only():
            print(f"\n  [INFO] {account_id} は draft_only です。提案はWAITING_REVIEW固定です。")
            if args.use_sheets and not args.mock:
                try:
                    results_to_analyze = load_measured_results_from_sheets(account_id, platform)
                except Exception as exc:
                    print(f"  [WARN] metrics read unavailable: {type(exc).__name__}")
                    results_to_analyze = []
            else:
                results_to_analyze = [
                    r for r in _MOCK_RESULTS if r.get("account_id") == account_id
                ] if args.mock else []
        elif args.use_sheets:
            try:
                results_to_analyze = load_measured_results_from_sheets(account_id, platform)
            except Exception as exc:
                print(f"  [WARN] metrics read unavailable: {type(exc).__name__}")
                results_to_analyze = []
        else:
            results_to_analyze = _MOCK_RESULTS if args.mock else []
    except FileNotFoundError:
        results_to_analyze = _MOCK_RESULTS if args.mock else []

    if not results_to_analyze and args.mock:
        results_to_analyze = [r for r in _MOCK_RESULTS if r.get("account_id") == account_id]

    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(
        results=results_to_analyze,
        account_id=account_id,
        platform=platform,
        days=args.days,
        generate_next_plan=args.generate_next_plan,
        max_suggestions=args.max_suggestions,
    )

    print("\n--- PDCA分析結果 ---")
    print(f"  pdca_run_id      : {result['pdca_run_id']}")
    print(f"  total_results    : {result['analysis']['total_results']}")
    print(f"  suggestion_count : {result['suggestion_count']}")
    print(f"  next_jobs_count  : {result['next_jobs_count']}")

    print("\n  コンテンツタイプ比較:")
    for ct, stats in result["analysis"]["content_type_comparison"].items():
        print(f"    {ct}: n={stats['count']} avg_er={stats['avg_engagement_rate']:.4f}")

    if result["improvement_suggestions"]:
        print("\n  改善提案（全て WAITING_REVIEW）:")
        for s in result["improvement_suggestions"]:
            print(f"    [{s['suggestion_id']}] {s['title']}")
            print(f"      {s['body'][:60]}...")
            print(f"      status={s['status']} active={s['active']}")

    if result["next_generation_jobs"]:
        print("\n  次回generation_jobs候補（全て PLANNED）:")
        for j in result["next_generation_jobs"]:
            print(f"    [{j['job_id']}] mode={j['generation_mode']} status={j['status']}")

    print("\n  安全注記:")
    for note in result["safety_notes"]:
        print(f"    - {note}")

    input_summary = pdca_input_summary(results_to_analyze) if args.use_sheets and not args.mock else {"metrics_status": "MOCK_OR_OFFLINE", "measured_result_count": len(results_to_analyze), "known_metric_value_count": 0}
    print(f"  metrics_input     : {input_summary['metrics_status']} ({input_summary['measured_result_count']})")

    if args.test_write or args.apply:
        print("\n--- test-write ---")
        if args.dry_run or not args.apply or not args.confirm_pdca:
            print("  [BLOCKED] PDCA audit write requires --no-dry-run --apply --confirm-pdca")
        elif args.use_sheets:
            try:
                from config_loader import get_config, get_config_partial
                from sheets_client import make_client
                try:
                    cfg = get_config()
                except ValueError:
                    cfg = get_config_partial()
                sheets = make_client(cfg, dry_run=False)
                sheets.append_row("pdca_runs", {
                    "pdca_run_id": result["pdca_run_id"],
                    "account_id": account_id,
                    "platform": platform,
                    "suggestion_count": result["suggestion_count"],
                    "created_at": result["created_at"],
                })
                print("  [OK] pdca_runs 書き込み完了")
            except Exception as e:
                print(f"  [WARN] Sheets write error: {type(e).__name__}")
        else:
            print(f"  [MockSheets] pdca_run を保存（mock）: {result['pdca_run_id']}")

    if args.output_json:
        print("\n--- JSON出力 ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n[DONE] run_pdca_cycle 完了")
    print("  実投稿なし / 自動反映なし / learning_rules active=false")


if __name__ == "__main__":
    main()
