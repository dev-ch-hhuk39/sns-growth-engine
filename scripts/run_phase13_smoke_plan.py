#!/usr/bin/env python3
"""run_phase13_smoke_plan.py — Phase 13 スモークプラン (dry_run=True がデフォルト)

使い方:
  python3 scripts/run_phase13_smoke_plan.py --account-id night_scout --platform x

全ステップを dry_run で実行して PASS/FAIL を確認する。
実投稿・実fetch・実ファイル書き込みはしない。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _section(title: str) -> None:
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 13 スモークプラン dry_run")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--platform", required=True, choices=["x", "threads"])
    args = parser.parse_args()

    run_id = f"SMOKE_{args.account_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    print(f"\n[PHASE13 SMOKE] account={args.account_id} platform={args.platform} dry_run=True")
    print(f"  run_id: {run_id}")

    step_results: list[dict] = []

    _section("Step 1: ToolDoctor")
    try:
        from src.reference.fetchers.tool_doctor import run_all_checks, print_report
        tool_results = run_all_checks()
        print_report(tool_results)
        not_installed = [r.name for r in tool_results if not r.installed]
        status = "WARN" if not_installed else "OK"
        step_results.append({"step": "tool_doctor", "status": status, "not_installed": not_installed})
        print(f"  → {status}")
    except Exception as e:
        print(f"  → ERROR: {e}")
        step_results.append({"step": "tool_doctor", "status": "ERROR", "error": str(e)})

    _section("Step 2: SourceToPostOrchestrator (mock=True, dry_run=True)")
    try:
        from src.orchestrators.source_to_post_orchestrator import run_pipeline
        pipeline_result = run_pipeline(
            account_id=args.account_id,
            platform=args.platform,
            mock=True,
            dry_run=True,
        )
        p_status = pipeline_result.get("status", "UNKNOWN")
        print(f"  → pipeline status: {p_status}")
        step_results.append({"step": "pipeline", "status": p_status})
    except Exception as e:
        print(f"  → ERROR: {e}")
        step_results.append({"step": "pipeline", "status": "ERROR", "error": str(e)})

    _section("Step 3: PipelineStore.save_summary (dry_run=True)")
    try:
        from src.storage.pipeline_store import PipelineStore
        store = PipelineStore()
        path = store.save_summary(run_id, {"smoke": True, "account_id": args.account_id}, dry_run=True)
        print(f"  → DRY_RUN path: {path}")
        step_results.append({"step": "pipeline_store", "status": "DRY_RUN"})
    except Exception as e:
        print(f"  → ERROR: {e}")
        step_results.append({"step": "pipeline_store", "status": "ERROR", "error": str(e)})

    _section("Step 4: Publisher dry_run")
    try:
        if args.platform == "threads":
            from src.publishers.threads_publisher import ThreadsPublisher
            publisher = ThreadsPublisher()
        else:
            from src.publishers.x_publisher import XPublisher
            publisher = XPublisher()
        result = publisher.publish(
            f"[SMOKE TEST] {run_id}",
            account={"account_id": args.account_id},
            derivative={"derivative_id": "smoke"},
            queue_item={"queue_id": "smoke"},
            dry_run=True,
        )
        p_status = "DRY_RUN" if result.is_dry_run_ok else ("OK" if result.success else "FAIL")
        print(f"  → publisher status: {p_status}")
        step_results.append({"step": "publisher", "status": p_status})
    except Exception as e:
        print(f"  → ERROR: {e}")
        step_results.append({"step": "publisher", "status": "ERROR", "error": str(e)})

    _section("Smoke Plan 結果")
    ok_statuses = {"OK", "DRY_RUN", "WARN", "BLOCKED", "WAITING_REVIEW"}
    all_ok = True
    for r in step_results:
        ok = r["status"] in ok_statuses
        flag = "✓" if ok else "✗"
        print(f"  {flag} {r['step']}: {r['status']}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("[SMOKE PASS] 全ステップが正常完了 (dry_run)")
        return 0
    print("[SMOKE FAIL] エラーあり。上記ログを確認してください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
