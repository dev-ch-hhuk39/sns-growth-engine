#!/usr/bin/env python3
"""Maintain strict READY candidates for every text slot in the next 24 hours."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from accounts.managed_accounts import account_choices  # noqa: E402
from config_loader import get_config  # noqa: E402
from content_schedule import text_slots  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402

JST = timezone(timedelta(hours=9))
PREPARED_ACCOUNTS = ("night_scout", "liver_manager")


def _extract_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    values: list[tuple[int, dict[str, Any]]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append((index + end, value))
    return [value for _end, value in sorted(values, key=lambda item: item[0])]


def next_text_slot(account_id: str, *, now: datetime | None = None) -> dict[str, str]:
    return future_text_slots(account_id, now=now, horizon_hours=24)[0]


def future_text_slots(
    account_id: str,
    *,
    now: datetime | None = None,
    horizon_hours: int = 24,
) -> list[dict[str, str]]:
    local = (now or datetime.now(JST)).astimezone(JST)
    choices: list[tuple[datetime, dict[str, str]]] = []
    for offset in (-1, 0, 1, 2):
        business_day = local.date() + timedelta(days=offset)
        for slot in text_slots(account_id):
            hour, minute = map(int, str(slot["target_jst"]).split(":"))
            target_day = business_day
            if hour >= 24:
                target_day += timedelta(days=1)
                hour -= 24
            target = datetime.combine(target_day, time(hour, minute), JST)
            if target >= local + timedelta(minutes=30):
                if target <= local + timedelta(hours=horizon_hours):
                    choices.append((target, {**slot, "business_date_jst": business_day.isoformat()}))
    if not choices:
        raise RuntimeError(f"no_future_text_slot:{account_id}")
    return [slot for _target, slot in sorted(choices, key=lambda item: item[0])]


def _ready_exists(rows: list[dict[str, Any]], account_id: str, slot: dict[str, str]) -> bool:
    target_date = str(slot["business_date_jst"])
    return any(
        str(row.get("account_id", "")) == account_id
        and str(row.get("slot_id", "")) == str(slot["slot_id"])
        and str(row.get("business_date_jst") or row.get("schedule_date_jst") or "")
        == target_date
        and str(row.get("status", "")).upper() == "READY"
        and str(row.get("validator_status", "")).upper() == "PASS"
        and str(row.get("internal_leak_status", "")).upper() == "PASS"
        and str(row.get("account_fit_status", "")).upper() == "PASS"
        for row in rows
    )


def _run(command: list[str]) -> tuple[int, dict[str, Any]]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    payloads = _extract_objects(completed.stdout)
    return completed.returncode, payloads[-1] if payloads else {}


def _generation_commands(account_id: str, slot: dict[str, str]) -> list[tuple[str, list[str]]]:
    base = [
        sys.executable,
        "scripts/generate_threads_ideas_from_references.py",
        "--account-id",
        account_id,
        "--apply",
        "--confirm-generate",
        "--top-n",
        "3",
        "--slot-id",
        str(slot["slot_id"]),
        "--post-type",
        str(slot["post_type"]),
        "--theme",
        str(slot.get("theme", "")),
        "--schedule-date-jst",
        str(slot["business_date_jst"]),
    ]
    original_fallback = [
        *base[: base.index("--post-type") + 1],
        "original_text",
        *base[base.index("--post-type") + 2 :],
    ]
    if slot["post_type"] == "pdca_text":
        return [
            ("measured_pdca", [*base, "--require-measured-pdca"]),
            ("safe_original_fallback", original_fallback),
        ]
    if slot["post_type"] == "reference_text":
        return [
            ("primary", base),
            ("safe_original_fallback", original_fallback),
        ]
    return [("primary", base)]


def replenish(account_id: str, slot: dict[str, str], *, apply: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "account_id": account_id,
        "slot_id": slot["slot_id"],
        "business_date_jst": slot["business_date_jst"],
        "post_type": slot["post_type"],
        "would_post": False,
    }
    if not apply:
        return {**result, "status": "PLAN_ONLY"}
    attempts: list[dict[str, str]] = []
    last_payload: dict[str, Any] = {}
    for generation_route, generation in _generation_commands(account_id, slot):
        rc, payload = _run(generation)
        last_payload = payload
        queue_ids = [
            str(value)
            for value in payload.get("effective_queue_ids", payload.get("queue_ids", []))
            if str(value)
        ]
        attempts.append({
            "route": generation_route,
            "status": str(payload.get("status", "")),
        })
        if rc != 0:
            continue
        for queue_id in queue_ids[:3]:
            ready_output = Path(f"/tmp/ready-inventory-{account_id}-{slot['slot_id']}.json")
            command = [
                sys.executable,
                "scripts/run_hybrid_ready_pipeline.py",
                "--account-id",
                account_id,
                "--slot-id",
                str(slot["slot_id"]),
                "--queue-id",
                queue_id,
                "--max-candidates",
                "1",
                "--approval-mode",
                "text",
                "--autonomous-low-risk",
                "--apply",
                "--use-sheets",
                "--json-output",
                str(ready_output),
            ]
            review_rc, review = _run(command)
            if ready_output.exists():
                review = json.loads(ready_output.read_text(encoding="utf-8"))
            attempts.append({
                "route": generation_route,
                "queue_id": queue_id,
                "status": str(review.get("status", "")),
            })
            if review_rc == 0 and review.get("status") == "READY":
                return {
                    **result,
                    "status": "READY_REPLENISHED",
                    "queue_id": queue_id,
                    "generation_route": generation_route,
                    "attempts": attempts,
                }
    return {
        **result,
        "status": "QUALITY_EXHAUSTED",
        "generation_status": str(last_payload.get("status", "")),
        "attempts": attempts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default="all", choices=account_choices(include_all=True))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-ready-maintenance", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply and (not args.confirm_ready_maintenance or not args.use_sheets):
        print(json.dumps({"status": "BLOCKED", "reason": "apply requires confirmation and --use-sheets"}))
        return 1
    if args.apply == args.dry_run:
        print(json.dumps({"status": "BLOCKED", "reason": "choose exactly one of --dry-run or --apply"}))
        return 1
    requested = PREPARED_ACCOUNTS if args.account_id == "all" else (args.account_id,)
    accounts = [account for account in requested if account in PREPARED_ACCOUNTS]
    queue_rows: list[dict[str, Any]] = []
    if args.use_sheets:
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        queue_rows = [dict(row) for row in read_records_safely(client, "queue")]
    results: list[dict[str, Any]] = []
    for account_id in accounts:
        for slot in future_text_slots(account_id):
            if _ready_exists(queue_rows, account_id, slot):
                results.append({
                    "account_id": account_id,
                    "slot_id": slot["slot_id"],
                    "business_date_jst": slot["business_date_jst"],
                    "status": "READY_INVENTORY_OK",
                })
                continue
            results.append(replenish(account_id, slot, apply=args.apply))
    if args.account_id in {"all", "beauty_account"}:
        results.append({
            "account_id": "beauty_account",
            "status": "DELEGATED_TO_BEAUTY_PREPARE_SCHEDULE",
            "workflow": "beauty-threads-production.yml",
        })
    failed = [row for row in results if row["status"] == "QUALITY_EXHAUSTED"]
    print(json.dumps({"status": "PASS" if not failed else "FAILED", "results": results, "would_post": False}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
