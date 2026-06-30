#!/usr/bin/env python3
"""Run safe growth loop planning without AUTOPOST."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    return {"cmd": " ".join(cmd), "returncode": p.returncode, "stdout": p.stdout, "stdout_tail": p.stdout[-1000:], "stderr_tail": p.stderr[-1000:]}


def _json_or_empty(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        return {}


def _plan_from_real_collection(account_id: str, source_result: dict[str, Any]) -> dict[str, Any]:
    rows = source_result.get("rows") or []
    if not rows:
        return {"status": "NO_DATA", "source_posts": 0, "scored_count": 0, "candidate_count": 0}

    sys.path.insert(0, str(ROOT / "scripts"))
    from score_reference_posts import build_scores
    from generate_threads_ideas_from_references import build_generation_rows

    accounts = ["night_scout", "liver_manager"] if account_id == "all" else [account_id]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    plans: list[dict[str, Any]] = []
    total_scores = 0
    total_candidates = 0
    for acct in accounts:
        acct_rows = [r for r in rows if str(r.get("account_id", "")) in {"", acct}]
        scores = build_scores(acct_rows, acct, stamp) if acct_rows else []
        generated = build_generation_rows(account_id=acct, posts=acct_rows, scores=scores, top_n=2) if scores else {"queue": []}
        queue = generated.get("queue", [])
        plans.append({
            "account_id": acct,
            "source_posts": len(acct_rows),
            "scored_count": len(scores),
            "candidate_count": len(queue),
            "candidate_statuses": sorted({str(q.get("status", "")) for q in queue}),
            "auto_publish_values": sorted({str(q.get("auto_publish", "")) for q in queue}),
        })
        total_scores += len(scores)
        total_candidates += len(queue)
    return {
        "status": "PLAN_ONLY",
        "source_posts": len(rows),
        "scored_count": total_scores,
        "candidate_count": total_candidates,
        "candidate_status": "WAITING_REVIEW",
        "auto_post": False,
        "plans": plans,
    }


def collect_adapter_status() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from collect_source_posts import adapter_status as source_adapter_status
    except Exception:
        source_adapter_status = lambda: {"source_adapters": "unavailable"}  # noqa: E731
    try:
        from collect_video_references import adapter_status as video_adapter_status
    except Exception:
        video_adapter_status = lambda: {"video_adapters": "unavailable"}  # noqa: E731
    try:
        from collect_threads_metrics import dependency_status as metrics_dependency_status
    except Exception:
        metrics_dependency_status = lambda: {"metrics_adapters": "unavailable"}  # noqa: E731
    return {
        "metrics": metrics_dependency_status(),
        "source": source_adapter_status(),
        "video": video_adapter_status(),
        "autopost": "off",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="run safe growth loop")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--metric-post-url", action="append", default=[])
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--fetch-real", action="store_true")
    args = parser.parse_args()
    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account outside growth loop"}, ensure_ascii=False))
        return 1
    if args.apply and not args.confirm_run:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-run"}, ensure_ascii=False))
        return 1
    tmp = Path(tempfile.gettempdir()) / "sns_growth_loop_empty_posted_results.json"
    tmp.write_text(json.dumps({"posted_results": []}), encoding="utf-8")
    source_cmd = [sys.executable, "scripts/collect_source_posts.py", "--account-id", args.account_id, "--platform", "threads", "--dry-run"]
    metrics_cmd = [sys.executable, "scripts/collect_threads_metrics.py", "--account-id", args.account_id, "--source", "browser", "--dry-run"]
    next_queue_cmd = [sys.executable, "scripts/generate_next_queue_from_metrics.py", "--account-id", "liver_manager" if args.account_id == "all" else args.account_id, "--dry-run"]
    if args.use_sheets:
        metrics_cmd += ["--use-sheets"]
        next_queue_cmd += ["--use-sheets"]
    else:
        next_queue_cmd += ["--input-json", str(tmp)]
    for url in args.metric_post_url:
        metrics_cmd += ["--post-url", url]
    for url in args.source_url:
        source_cmd += ["--source-url", url]
    if args.fetch_real:
        source_cmd += ["--fetch-real"]
    steps = [
        metrics_cmd,
        next_queue_cmd,
        source_cmd,
        [sys.executable, "scripts/generate_media_post_queue.py", "--account-id", args.account_id, "--dry-run"],
        [sys.executable, "scripts/run_autopilot_loop.py", "--dry-run", "--account-id", args.account_id, "--auto-ready", "--skip-real-post"],
    ]
    results = [_run(cmd) for cmd in steps]
    source_result = _json_or_empty(results[2].get("stdout", ""))
    real_collection_pipeline = _plan_from_real_collection(args.account_id, source_result)
    for result in results:
        result.pop("stdout", None)
    print(json.dumps({
        "status": "PLAN_ONLY",
        "account_id": args.account_id,
        "auto_post": False,
        "kill_switch_respected": True,
        "real_post": False,
        "adapter_status": collect_adapter_status(),
        "real_collection_pipeline": real_collection_pipeline,
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
