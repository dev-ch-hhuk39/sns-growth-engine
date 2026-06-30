#!/usr/bin/env python3
"""Run safe growth loop planning without AUTOPOST."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    return {"cmd": " ".join(cmd), "returncode": p.returncode, "stdout_tail": p.stdout[-1000:], "stderr_tail": p.stderr[-1000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="run safe growth loop")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account outside growth loop"}, ensure_ascii=False))
        return 1
    if args.apply and not args.confirm_run:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-run"}, ensure_ascii=False))
        return 1
    tmp = Path(tempfile.gettempdir()) / "sns_growth_loop_empty_posted_results.json"
    tmp.write_text(json.dumps({"posted_results": []}), encoding="utf-8")
    steps = [
        [sys.executable, "scripts/collect_threads_metrics.py", "--account-id", args.account_id, "--dry-run"],
        [sys.executable, "scripts/generate_next_queue_from_metrics.py", "--account-id", "liver_manager" if args.account_id == "all" else args.account_id, "--dry-run", "--input-json", str(tmp)],
        [sys.executable, "scripts/collect_source_posts.py", "--account-id", args.account_id, "--platform", "all", "--dry-run"],
        [sys.executable, "scripts/generate_media_post_queue.py", "--account-id", args.account_id, "--dry-run"],
        [sys.executable, "scripts/run_autopilot_loop.py", "--dry-run", "--account-id", args.account_id, "--auto-ready", "--skip-real-post"],
    ]
    results = [_run(cmd) for cmd in steps]
    print(json.dumps({
        "status": "PLAN_ONLY",
        "account_id": args.account_id,
        "auto_post": False,
        "kill_switch_respected": True,
        "real_post": False,
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
