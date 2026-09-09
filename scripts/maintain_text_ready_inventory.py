#!/usr/bin/env python3
"""Prepare buffered, strictly approved text inventory outside the publish path."""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from accounts.managed_accounts import account_choices  # noqa: E402
from config_loader import get_config  # noqa: E402
from content_schedule import MEDIA_POST_TYPES, text_slots  # noqa: E402
from production_inventory import eligible_ready, has_media, scheduled_slots  # noqa: E402
from hybrid_ai_gate import hybrid_ai_gate_passed  # noqa: E402
from hybrid_ai_source_context import build_source_context  # noqa: E402
from public_post_quality import final_public_post_validator  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import enable_readonly_record_cache, read_records_safely  # noqa: E402
from production_inventory import policy  # noqa: E402

JST = timezone(timedelta(hours=9))
PREPARED_ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")


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
    if not 1 <= horizon_hours <= 168:
        raise ValueError("inventory_horizon_must_be_1_to_168_hours")
    for offset in range(-1, horizon_hours // 24 + 2):
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
    try:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=480,
            env={**os.environ, "BUFFERED_PREPARATION": "true", "PUBLISH_ENABLED": "false", "ALLOW_REAL_THREADS_POST": "false"})
    except subprocess.TimeoutExpired:
        return 124, {"status": "FAILED", "failure_category": "GENERATION_PROCESS_TIMEOUT"}
    payloads = _extract_objects(completed.stdout)
    payload = payloads[-1] if payloads else {}
    # Preserve a safe error category, never the provider response or credentials.
    error = completed.stderr
    if "hybrid_ai_budget_blocked:" in error:
        payload["failure_category"] = "AI_APPROVAL_BUDGET_EXHAUSTED"
    elif "RESOURCE_EXHAUSTED" in error or "HTTP 429" in error:
        payload["failure_category"] = "PROVIDER_RATE_LIMITED"
    elif "Timeout" in error or "timed out" in error:
        payload["failure_category"] = "PROVIDER_TIMEOUT"
    elif completed.returncode:
        payload.setdefault("failure_category", "GENERATION_PROCESS_FAILED")
    return completed.returncode, payload


def _generation_commands(account_id: str, slot: dict[str, str]) -> list[tuple[str, list[str]]]:
    if account_id == "beauty_account":
        from content_schedule import slots_for_account
        index = next(i for i, row in enumerate(slots_for_account(account_id)) if row["slot_id"] == slot["slot_id"])
        return [(f"beauty_reserve_{candidate}", [sys.executable, "scripts/prepare_beauty_review_candidates.py",
            "--slot-index", str(index), "--schedule-date-jst", str(slot["business_date_jst"]),
            "--candidate-index", str(candidate), "--apply", "--confirm-prepare"]) for candidate in range(3)]
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


def replenish(account_id: str, slot: dict[str, str], *, apply: bool,
              required: int = 1) -> dict[str, Any]:
    if not 1 <= required <= 3:
        raise ValueError("inventory_required_must_be_1_to_3")
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
    approved: list[str] = []
    last_payload: dict[str, Any] = {}
    for generation_route, generation in _generation_commands(account_id, slot):
        rc, payload = _run(generation)
        last_payload = payload
        queue_ids = [
            str(value)
            for value in payload.get("effective_queue_ids", payload.get("queue_ids", []))
            if str(value)
        ]
        if account_id == "beauty_account" and payload.get("apply_result", {}).get("read_after_write"):
            queue_ids = [str(payload["apply_result"]["queue_id"])]
        attempts.append({
            "route": generation_route,
            "status": str(payload.get("status", "")),
            "reason": str(payload.get("failure_category") or payload.get("reason") or ""),
        })
        if rc != 0:
            continue
        for queue_id in queue_ids[:3]:
            if queue_id in approved:
                continue
            ready_output = Path(f"/tmp/ready-inventory-{account_id}-{slot['slot_id']}.json")
            # A failed subprocess must not inherit a previous candidate's READY.
            ready_output.unlink(missing_ok=True)
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
                "reason": str(review.get("failure_category") or review.get("reason") or ""),
            })
            if review_rc == 0 and review.get("status") == "READY":
                approved.append(queue_id)
                if len(approved) >= required:
                    return {
                        **result,
                        "status": "READY_REPLENISHED",
                        "queue_id": approved[0],
                        "queue_ids": approved,
                        "generation_route": generation_route,
                        "attempts": attempts,
                    }
    return {
        **result,
        "status": "QUALITY_EXHAUSTED",
        "queue_ids": approved,
        "missing": required - len(approved),
        "generation_status": str(last_payload.get("status", "")),
        "failure_category": str(last_payload.get("failure_category") or "QUALITY_EXHAUSTED"),
        "attempts": attempts,
    }


def replenish_bank(client, account_id: str, *, apply: bool) -> dict[str, Any]:
    from evergreen_inventory import admit_bank_batch
    from process_threads_queue import process_one, records
    from sheets_client import TAB_DEFINITIONS
    from production_inventory import select_evergreen
    from generate_threads_ideas_from_references import original_text_similarity_guard

    now = datetime.now(JST)
    minimum = policy()["minimum_evergreen_per_account"]
    if not apply:
        return {"status": "PLAN_ONLY", "account_id": account_id, "minimum": minimum, "would_post": False}
    client._ensure_tab("evergreen_bank", TAB_DEFINITIONS["evergreen_bank"])
    snapshot = copy.copy(client)
    enable_readonly_record_cache(snapshot)

    def check(row):
        return (final_public_post_validator(str(row.get("public_post_text", "")), account_id).get("status") == "PASS"
                and hybrid_ai_gate_passed(row, build_source_context(snapshot, row))[0]
                and process_one(snapshot, row, dry_run=True, confirm_real_post=False).get("status") == "DRY_RUN")

    posted_ids = {r.get("queue_id") for r in records(client, "posted_results")}
    existing_bank_ids = {r.get("queue_id") for r in records(client, "evergreen_bank")}
    canonical_queues = records(client, "queue")
    admissions = []
    for row in canonical_queues:
        date = str(row.get("business_date_jst") or row.get("schedule_date_jst") or "")
        if (sum(r.get("queue_id") == row.get("queue_id") for r in canonical_queues) != 1
                or row.get("queue_id") in posted_ids or row.get("queue_id") in existing_bank_ids
                or row.get("generation_mode") not in {"original_text", "beauty_new_text_generation", "new_text_generation"}
                or not eligible_ready(row, account_id) or has_media(row)
                or (date and date >= now.date().isoformat()) or not check(row)):
            continue
        admissions.append(row)
        if len(admissions) >= minimum:
            break
    if admissions:
        admit_bank_batch(client, admissions, now=now, runtime_check=check, apply=True)

    def count_usable():
        bank, queues, posted = records(client, "evergreen_bank"), records(client, "queue"), records(client, "posted_results")
        unallocated = [r for r in queues if not (r.get("business_date_jst") or r.get("schedule_date_jst"))]
        usable = set()
        for entry in bank:
            value = select_evergreen([entry], unallocated, posted, account=account_id, now=now,
                runtime_check=check, similar=lambda a, b: original_text_similarity_guard(a, b)["status"] == "BLOCKED")
            if value:
                usable.add(value["normalized_hash"])
        return len(usable)

    current, attempts = count_usable(), []
    # Temporary future allocation prevents an approved candidate from becoming
    # today's publish target during the two-phase bank admission.
    slot = next((r for r in text_slots(account_id) if r["post_type"] == "original_text"), text_slots(account_id)[0])
    slot = {**slot, "business_date_jst": (now.date() + timedelta(days=7)).isoformat()}
    for _ in range(10):
        if current >= minimum:
            break
        result = replenish(account_id, slot, apply=True, required=min(3, minimum-current))
        attempts.append({"status": result["status"], "queue_ids": result.get("queue_ids", [])})
        generated_rows = records(client, "queue") if result.get("queue_ids") else []
        admissions = []
        for qid in result.get("queue_ids", []):
            matches = [r for r in generated_rows if r.get("queue_id") == qid]
            if len(matches) != 1 or not eligible_ready(matches[0], account_id) or not check(matches[0]):
                raise RuntimeError("EVERGREEN_APPROVAL_READ_AFTER_WRITE_FAILED")
            admissions.append(matches[0])
        if admissions:
            admit_bank_batch(client, admissions, now=now, runtime_check=check, apply=True)
        current = count_usable()
        if not result.get("queue_ids"):
            break
    return {"status": "READY_INVENTORY_OK" if current >= minimum else "QUALITY_EXHAUSTED",
            "account_id": account_id, "usable_evergreen": current, "minimum": minimum,
            "attempts": attempts, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default="all", choices=account_choices(include_all=True))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-ready-maintenance", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--horizon-hours", type=int, default=policy()["text_horizon_hours"])
    parser.add_argument("--evergreen-bank", action="store_true")
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
        if args.apply:
            from sheets_client import TAB_DEFINITIONS
            client._ensure_tab("evergreen_bank", TAB_DEFINITIONS["evergreen_bank"])
    results: list[dict[str, Any]] = []
    for account_id in accounts:
        if args.evergreen_bank:
            results.append(replenish_bank(client if args.use_sheets else None, account_id, apply=args.apply))
            continue
        now = datetime.now(JST)
        slots = scheduled_slots(account_id, now, now + timedelta(hours=args.horizon_hours))
        for expected_slot in slots:
            snapshot = copy.copy(client) if args.use_sheets else None
            if snapshot is not None:
                enable_readonly_record_cache(snapshot)
            # Only the reserve generation route changes. The canonical slot
            # remains media and delivery must explicitly report text fallback.
            slot = {**expected_slot, "post_type": "original_text"} if expected_slot["post_type"] in MEDIA_POST_TYPES else expected_slot
            ready_ids = {str(row["queue_id"]) for row in queue_rows
                         if eligible_ready(row, account_id) and not has_media(row)
                         and _ready_exists([row], account_id, slot)
                         and final_public_post_validator(str(row["public_post_text"]), account_id).get("status") == "PASS"
                         and hybrid_ai_gate_passed(row, build_source_context(snapshot, row))[0]}
            missing = max(0, policy()["text_candidates_per_slot"] - len(ready_ids))
            if not missing:
                results.append({
                    "account_id": account_id,
                    "slot_id": slot["slot_id"],
                    "business_date_jst": slot["business_date_jst"],
                    "status": "READY_INVENTORY_OK",
                })
                continue
            result = replenish(account_id, slot, apply=args.apply, required=missing)
            if args.apply and result["status"] == "QUALITY_EXHAUSTED":
                from evergreen_inventory import allocate_bank_candidate
                from generate_threads_ideas_from_references import original_text_similarity_guard
                recovered = list(result.get("queue_ids", []))
                # Refresh once after generation; reuse read-only source evidence across reserves.
                snapshot = copy.copy(client)
                enable_readonly_record_cache(snapshot)
                for _ in range(max(0, missing - len(recovered))):
                    allocated = allocate_bank_candidate(client, account=account_id, slot=slot, now=now, apply=True,
                        runtime_check=lambda row: hybrid_ai_gate_passed(row, build_source_context(snapshot, row))[0]
                            and final_public_post_validator(str(row.get("public_post_text", "")), account_id).get("status") == "PASS",
                        similar=lambda a, b: original_text_similarity_guard(a, b)["status"] == "BLOCKED")
                    if allocated["status"] != "ALLOCATED":
                        break
                    recovered.append(allocated["queue_id"])
                result["queue_ids"] = recovered
                if len(recovered) >= missing:
                    result.update(status="READY_REPLENISHED", generation_route="validated_evergreen_fallback")
            results.append(result)
    failed = [row for row in results if row["status"] == "QUALITY_EXHAUSTED"]
    print(json.dumps({"status": "PASS" if not failed else "FAILED", "results": results, "would_post": False}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
