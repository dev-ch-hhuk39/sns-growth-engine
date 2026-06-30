#!/usr/bin/env python3
"""Autopilot runner for the safe SNS Growth Engine loop.

Initial autopilot scope:
- verify
- reference seed/score/idea generation planning
- AUTO_READY
- worker dry-run
- PDCA dry-run

AUTO_POST is a separate opt-in path and still requires the worker triple gate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = ROOT / "config/auto_approval_rules.json"


def _run(cmd: list[str]) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "cmd": " ".join(cmd),
        "returncode": p.returncode,
        "stdout_tail": p.stdout[-1200:],
        "stderr_tail": p.stderr[-1200:],
    }


def load_rules(path: Path = RULES_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def auto_post_gate(args: argparse.Namespace, rules: dict[str, Any]) -> dict[str, Any]:
    defaults = rules.get("defaults", {})
    enabled_by_rules = bool(defaults.get("auto_post_enabled", False))
    requested = bool(args.auto_post)
    env_ok = (
        os.environ.get("PUBLISH_ENABLED", "").lower() == "true"
        and os.environ.get("ALLOW_REAL_THREADS_POST", "").lower() == "true"
    )
    confirm = bool(args.confirm_real_post)
    allowed = requested and enabled_by_rules and env_ok and confirm and not args.skip_real_post
    return {
        "auto_post_requested": requested,
        "auto_post_enabled": enabled_by_rules,
        "env_gate_ok": env_ok,
        "confirm_real_post": confirm,
        "skip_real_post": bool(args.skip_real_post),
        "allowed": allowed,
    }


def build_plan(args: argparse.Namespace, rules: dict[str, Any]) -> dict[str, Any]:
    accounts = ["night_scout", "liver_manager"] if args.account_id == "all" else [args.account_id]
    gate = auto_post_gate(args, rules)
    return {
        "status": "PLAN_ONLY" if not (args.apply and args.confirm_run) else "WILL_RUN",
        "account_id": args.account_id,
        "accounts": accounts,
        "auto_ready": bool(args.auto_ready),
        "auto_post_gate": gate,
        "steps": [
            "verify",
            "seed_reference_posts",
            "score_reference_posts",
            "generate_threads_ideas",
            "auto_approve_queue" if args.auto_ready else "skip_auto_ready",
            "process_threads_queue_dry_run",
            "pdca_dry_run",
        ],
        "safety": {
            "x_fetch": False,
            "x_post": False,
            "beauty_account": False,
            "video_download": False,
            "cloudinary_upload": False,
            "auto_post_separate_gate": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="run safe autopilot loop")
    parser.add_argument("--dry-run", action="store_true", help="plan only (default)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--auto-ready", action="store_true")
    parser.add_argument("--auto-post", action="store_true")
    parser.add_argument("--max-ready", type=int, default=1)
    parser.add_argument("--max-posts", type=int, default=1)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--skip-real-post", action="store_true")
    parser.add_argument("--confirm-real-post", action="store_true")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account is outside autopilot"}, ensure_ascii=False))
        return 1

    rules = load_rules()
    plan = build_plan(args, rules)
    results: list[dict[str, Any]] = []

    if not (args.apply and args.confirm_run):
        if args.use_sheets:
            results.append(_run([sys.executable, "scripts/recover_production_sheets_threads_first.py", "--verify-only", "--json"]))
            if args.auto_ready:
                results.append(_run([sys.executable, "scripts/auto_approve_queue.py", "--dry-run", "--account-id", args.account_id, "--max-ready", str(args.max_ready), "--use-sheets"]))
            for acct in plan["accounts"]:
                results.append(_run([sys.executable, "scripts/process_threads_queue.py", "--account-id", acct, "--dry-run", "--max-posts", str(min(args.max_posts, 2))]))
                results.append(_run([sys.executable, "scripts/generate_next_queue_from_metrics.py", "--account-id", acct, "--count", "1", "--dry-run"]))
        print(json.dumps({"mode": "dry-run", **plan, "results": results}, ensure_ascii=False, indent=2))
        return 0

    results.append(_run([sys.executable, "scripts/recover_production_sheets_threads_first.py", "--verify-only", "--json"]))
    if args.auto_ready:
        results.append(_run([sys.executable, "scripts/auto_approve_queue.py", "--apply", "--confirm-auto-ready", "--account-id", args.account_id, "--max-ready", str(args.max_ready), "--use-sheets"]))

    gate = plan["auto_post_gate"]
    if gate["allowed"]:
        for acct in plan["accounts"]:
            results.append(_run([sys.executable, "scripts/process_threads_queue.py", "--account-id", acct, "--confirm-real-post", "--max-posts", str(min(args.max_posts, 1))]))
    else:
        for acct in plan["accounts"]:
            results.append(_run([sys.executable, "scripts/process_threads_queue.py", "--account-id", acct, "--dry-run", "--max-posts", str(min(args.max_posts, 2))]))
    print(json.dumps({"status": "DONE", **plan, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
