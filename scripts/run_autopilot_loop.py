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
sys.path.insert(0, str(ROOT / "src"))

from accounts.managed_accounts import account_choices  # noqa: E402
from autonomous_runtime_config import load_runtime_policy  # noqa: E402
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
    if path == RULES_FILE:
        return load_runtime_policy()[1]
    return json.loads(path.read_text(encoding="utf-8"))


def auto_post_gate(args: argparse.Namespace, rules: dict[str, Any]) -> dict[str, Any]:
    autonomous, canonical_rules = load_runtime_policy()
    if rules.get("publication_control") != canonical_rules.get("publication_control"):
        raise RuntimeError("auto approval rules cannot override publication authority")
    enabled_by_rules = bool(autonomous.get("auto_post_enabled", False))
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
    accounts = list(account_choices()) if args.account_id == "all" else [args.account_id]
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
            "account_isolation": True,
            "video_download": False,
            "cloudinary_upload": False,
            "auto_post_separate_gate": True,
        },
    }


def _report_outcome(plan: dict[str, Any], results: list[dict[str, Any]], *,
                    mode: str, summary_only: bool) -> int:
    """Propagate nested command failures, never log raw child output in CI."""
    failed_steps = sum(
        type(result.get("returncode")) is not int or result["returncode"] != 0
        for result in results
    )
    status = "FAILED" if failed_steps else ("DONE" if mode == "apply" else "PLAN_ONLY")
    if summary_only:
        # Fixed fields only: do not expose subprocess commands, unpublished
        # queue IDs, captions, Sheets data, stdout/stderr, or provider text.
        report = {
            "status": "FAILED" if failed_steps else "PASS",
            "mode": mode,
            "account_id": plan["account_id"],
            "steps_checked": len(results),
            "failed_steps": failed_steps,
            "real_post_allowed": plan["auto_post_gate"]["allowed"],
        }
        if plan.get("ready_only"):
            # Static stage categories only, never child stdout/stderr.
            names = ("TEXT_PREFLIGHT", "AUTO_READY_APPLY", "TEXT_POSTVERIFY")
            report["stage_statuses"] = [
                {"stage": name, "status": "PASS" if i < len(results)
                 and type(results[i].get("returncode")) is int
                 and results[i]["returncode"] == 0 else
                 ("NOT_RUN" if i >= len(results) else "FAILED")}
                for i, name in enumerate(names)
            ]
    else:
        # The final status must override plan["status"] ("WILL_RUN").
        report = {**plan, "status": status, "results": results}
        if mode == "dry-run":
            report["mode"] = mode
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed_steps else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="run safe autopilot loop")
    parser.add_argument("--dry-run", action="store_true", help="plan only (default)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--account-id", default="all", choices=account_choices(include_all=True))
    parser.add_argument("--auto-ready", action="store_true")
    parser.add_argument("--auto-post", action="store_true")
    parser.add_argument("--max-ready", type=int, default=1)
    parser.add_argument("--max-posts", type=int, default=1)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--skip-real-post", action="store_true")
    parser.add_argument("--confirm-real-post", action="store_true")
    parser.add_argument(
        "--ready-only", action="store_true",
        help="Single-account, no-post text READY maintenance; no unrelated media/publisher validation",
    )
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Print only fixed, redacted CI status fields; never child output",
    )
    args = parser.parse_args()

    # Explicit authority only for a no-post single-account READY writer.
    if args.ready_only and not (
        args.apply and args.confirm_run and args.auto_ready
        and args.skip_real_post and not args.auto_post
        and not args.confirm_real_post and args.use_sheets
        and args.account_id != "all" and 1 <= args.max_ready <= 3
    ):
        print(json.dumps({"status": "BLOCKED", "reason": "READY_ONLY_SCOPE_INVALID"}))
        return 2
    rules = load_rules()
    plan = build_plan(args, rules)
    results: list[dict[str, Any]] = []

    if args.ready_only:
        plan["ready_only"] = True
        verify_text = [
            sys.executable, "scripts/recover_production_sheets_threads_first.py",
            "--verify-only", "--text-inventory-scope",
            "--account-id", args.account_id, "--json",
        ]
        preflight = _run(verify_text)
        results.append(preflight)
        if preflight.get("returncode") != 0:
            return _report_outcome(plan, results, mode="apply",
                                   summary_only=args.summary_only)
        results.append(_run([
            sys.executable, "scripts/auto_approve_queue.py",
            "--apply", "--confirm-auto-ready",
            "--account-id", args.account_id,
            "--max-ready", str(args.max_ready),
            "--use-sheets", "--skip-setup",
        ]))
        # Reverify even if the READY write returned an ambiguous failure.
        results.append(_run(verify_text))
        return _report_outcome(plan, results, mode="apply",
                               summary_only=args.summary_only)

    if not (args.apply and args.confirm_run):
        if args.use_sheets:
            results.append(_run([sys.executable, "scripts/recover_production_sheets_threads_first.py", "--verify-only", "--json"]))
            if args.auto_ready:
                results.append(_run([sys.executable, "scripts/auto_approve_queue.py", "--dry-run", "--account-id", args.account_id, "--max-ready", str(args.max_ready), "--use-sheets"]))
            for acct in plan["accounts"]:
                results.append(_run([sys.executable, "scripts/process_threads_queue.py", "--account-id", acct, "--dry-run", "--max-posts", str(min(args.max_posts, 2))]))
                results.append(_run([sys.executable, "scripts/generate_next_queue_from_metrics.py", "--account-id", acct, "--count", "1", "--dry-run"]))
        return _report_outcome(plan, results, mode="dry-run",
                               summary_only=args.summary_only)

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
    return _report_outcome(plan, results, mode="apply",
                           summary_only=args.summary_only)


if __name__ == "__main__":
    raise SystemExit(main())
