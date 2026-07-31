#!/usr/bin/env python3
"""Reconcile exact canary posted-results verification without posting."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from config_loader import get_config
from final_production_contracts import (
    ACCOUNTS,
    CANARY_TYPES,
    activation_evidence,
    canary_id,
)
from process_threads_queue import now_iso, records, update_row
from sheets_client import SheetsClient

FIRST_WAVE_TYPES = {
    "original_text",
    "direct_image",
}
ACCEPTED_VERIFICATION = {
    "PASS",
    "VERIFIED",
    "READ_AFTER_WRITE_PASS",
}
REQUIRED_WINDOWS = {24, 72, 168}


def _slot(row: dict[str, Any]) -> tuple[str, str] | None:
    account_id = str(row.get("account_id", "")).strip()
    content_type = str(
        row.get("content_type")
        or row.get("generation_mode")
        or ""
    ).strip()

    if account_id in ACCOUNTS and content_type in CANARY_TYPES:
        return account_id, content_type

    candidate = str(row.get("canary_id", "")).strip()
    for expected_account in ACCOUNTS:
        for expected_type in CANARY_TYPES:
            if (
                candidate == canary_id(
                    expected_account,
                    expected_type,
                )
                or candidate.endswith(
                    f"_{expected_account}_{expected_type}"
                )
            ):
                return expected_account, expected_type

    return None


def _window(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def build_plan(
    posted_results: list[dict[str, Any]],
    metric_jobs: list[dict[str, Any]],
    *,
    first_wave_batch_id: str,
    remaining_batch_id: str,
) -> dict[str, Any]:
    expected_slots = [
        (account_id, content_type)
        for account_id in ACCOUNTS
        for content_type in CANARY_TYPES
    ]

    metrics_by_canary: dict[str, set[int]] = {}
    for job in metric_jobs:
        status = str(job.get("status", "")).upper()
        if status in {"FAILED", "CANCELLED"}:
            continue
        candidate = str(job.get("canary_id", "")).strip()
        if candidate:
            metrics_by_canary.setdefault(candidate, set()).add(
                _window(job.get("window_hours"))
            )

    plan_rows: list[dict[str, Any]] = []

    for account_id, content_type in expected_slots:
        expected_batch_id = (
            first_wave_batch_id
            if content_type in FIRST_WAVE_TYPES
            else remaining_batch_id
        )

        matches = [
            row
            for row in posted_results
            if _slot(row) == (account_id, content_type)
            and str(row.get("batch_id", "")).strip()
            == expected_batch_id
        ]

        reasons: list[str] = []

        if len(matches) != 1:
            reasons.append(
                "POSTED_RESULT_MISSING"
                if not matches
                else "AMBIGUOUS_POSTED_RESULTS"
            )
            selected: dict[str, Any] = {}
        else:
            selected = matches[0]

        required_fields = (
            "result_id",
            "queue_id",
            "canary_id",
            "post_url",
            "external_post_id",
        )

        if selected:
            if str(selected.get("status", "")).upper() != "POSTED":
                reasons.append("RESULT_STATUS_NOT_POSTED")

            for field in required_fields:
                if not str(selected.get(field, "")).strip():
                    reasons.append(
                        f"{field.upper()}_MISSING"
                    )

        selected_canary_id = str(
            selected.get("canary_id", "")
        ).strip()

        if (
            selected_canary_id
            and not REQUIRED_WINDOWS
            <= metrics_by_canary.get(selected_canary_id, set())
        ):
            reasons.append("METRIC_WINDOWS_INCOMPLETE")

        current_verification = str(
            selected.get("verification_status", "")
        ).upper()

        action = (
            "SKIP_ALREADY_VERIFIED"
            if current_verification in ACCEPTED_VERIFICATION
            else "UPDATE_VERIFICATION"
        )

        plan_rows.append(
            {
                "account_id": account_id,
                "content_type": content_type,
                "expected_batch_id": expected_batch_id,
                "result_id": selected.get("result_id", ""),
                "queue_id": selected.get("queue_id", ""),
                "canary_id": selected_canary_id,
                "current_verification_status": (
                    current_verification
                ),
                "action": action,
                "status": (
                    "READY_TO_RECONCILE"
                    if not reasons
                    else "BLOCKED"
                ),
                "reasons": sorted(set(reasons)),
            }
        )

    return {
        "status": (
            "PASS"
            if len(plan_rows) == 12
            and all(
                row["status"] == "READY_TO_RECONCILE"
                for row in plan_rows
            )
            else "BLOCKED"
        ),
        "expected_count": 12,
        "row_count": len(plan_rows),
        "first_wave_batch_id": first_wave_batch_id,
        "remaining_batch_id": remaining_batch_id,
        "rows": plan_rows,
        "would_post": False,
    }


def apply_plan(
    client: SheetsClient,
    plan: dict[str, Any],
) -> dict[str, Any]:
    if plan.get("status") != "PASS":
        return {
            "status": "BLOCKED",
            "plan": plan,
            "would_post": False,
        }

    failures: list[str] = []

    for row in plan["rows"]:
        if row["action"] == "SKIP_ALREADY_VERIFIED":
            continue

        result_id = str(row["result_id"])

        saved = update_row(
            client,
            "posted_results",
            "result_id",
            result_id,
            {
                "verification_status": (
                    "READ_AFTER_WRITE_PASS"
                ),
                "verification_checked_at": now_iso(),
            },
        )

        if not saved:
            failures.append(result_id)

    posted_after = records(client, "posted_results")
    jobs_after = records(client, "metrics_collection_jobs")
    activation = activation_evidence(
        posted_after,
        jobs_after,
    )

    return {
        "status": (
            "APPLIED"
            if not failures
            and activation.get("status")
            == "READY_FOR_ACTIVATION"
            else "PARTIAL_FAILED"
        ),
        "updated_result_count": sum(
            row["action"] == "UPDATE_VERIFICATION"
            for row in plan["rows"]
        ),
        "failed_result_ids": failures,
        "activation_guard": activation,
        "would_post": False,
        "plan": plan,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    mode = parser.add_mutually_exclusive_group(
        required=True,
    )
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")

    parser.add_argument(
        "--confirm-reconcile-read-after-write",
        action="store_true",
    )
    parser.add_argument(
        "--first-wave-batch-id",
        required=True,
    )
    parser.add_argument(
        "--remaining-batch-id",
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    if (
        args.apply
        and not args.confirm_reconcile_read_after_write
    ):
        result = {
            "status": "BLOCKED",
            "reason": (
                "--confirm-reconcile-read-after-write "
                "required for --apply"
            ),
            "would_post": False,
        }
    else:
        config = get_config()
        client = SheetsClient(
            config["sheet_id"],
            config["sa_dict"],
            dry_run=False,
        )

        posted_results = records(
            client,
            "posted_results",
        )
        metric_jobs = records(
            client,
            "metrics_collection_jobs",
        )

        plan = build_plan(
            posted_results,
            metric_jobs,
            first_wave_batch_id=(
                args.first_wave_batch_id
            ),
            remaining_batch_id=(
                args.remaining_batch_id
            ),
        )

        result = (
            apply_plan(client, plan)
            if args.apply
            else {
                "status": (
                    "PLAN_ONLY"
                    if plan["status"] == "PASS"
                    else "BLOCKED"
                ),
                "plan": plan,
                "would_post": False,
            }
        )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": result.get("status"),
                "would_post": False,
            },
            ensure_ascii=False,
        )
    )

    return (
        0
        if result.get("status")
        in {"PLAN_ONLY", "APPLIED"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
