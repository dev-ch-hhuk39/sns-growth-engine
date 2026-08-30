#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "src"),
    str(ROOT / "scripts"),
]

from accounts.managed_accounts import (  # noqa: E402
    account_allows_autonomous_ready,
    account_choices,
)
from run_hybrid_ready_pipeline import execute  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promote one strictly validated autonomous-low-risk "
            "Direct Media queue to READY without publishing it."
        )
    )

    parser.add_argument(
        "--account-id",
        required=True,
        choices=account_choices(),
    )

    parser.add_argument(
        "--slot-id",
        required=True,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--confirm-autonomous-ready",
        action="store_true",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--use-sheets",
        action="store_true",
    )

    parser.add_argument(
        "--output",
        default="",
    )

    args = parser.parse_args()

    if args.apply == args.dry_run:
        raise RuntimeError(
            "specify exactly one of --apply or --dry-run"
        )

    if (
        args.apply
        and not args.confirm_autonomous_ready
    ):
        raise RuntimeError(
            "--apply requires --confirm-autonomous-ready"
        )

    if not args.use_sheets:
        raise RuntimeError(
            "--use-sheets is required"
        )

    if not account_allows_autonomous_ready(args.account_id):
        raise RuntimeError(
            "autonomous_low_risk_not_allowed_for_account"
        )

    result = execute(
        args.account_id,
        args.slot_id,
        1,
        apply=args.apply,
        approval_mode="media",
        autonomous_low_risk=True,
    )

    status = str(
        result.get(
            "status",
            "",
        )
    )

    if status == "READY":
        payload = {
            **result,
            "automation_status":
                "AUTONOMOUS_READY",
            "would_post": False,
        }
        exit_code = 0

    elif status == "NO_READY_CANDIDATE":
        payload = {
            **result,
            "automation_status":
                "NO_ELIGIBLE_CANDIDATE",
            "would_post": False,
        }
        exit_code = 0

    else:
        payload = {
            **result,
            "automation_status":
                "FAILED",
            "would_post": False,
        }
        exit_code = 2

    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )

    print(rendered)

    if args.output:
        Path(
            args.output
        ).write_text(
            rendered + "\n",
            encoding="utf-8",
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
