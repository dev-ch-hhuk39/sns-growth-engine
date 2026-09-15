"""Persist unused, already-approved canonical text candidates without LLM calls."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

from production_inventory import eligible_ready, has_media, hashes, policy, select_evergreen


_AMBIGUOUS_SLOT_STATUSES = {
    "RECOVERY_REQUIRED", "POSTED_SAVE_UNVERIFIED", "PUBLISH_OUTCOME_UNVERIFIED",
}


def expired_unpublished_bank_allocations(
    entries: list[dict],
    queues: list[dict],
    posted: list[dict],
    slot_runs: list[dict],
    *,
    current_business_date: str,
) -> list[dict]:
    """Plan safe reserve releases for missed slots outside the recovery window.

    A bank candidate allocated to a past slot cannot be counted or consumed
    again.  It may only return to the unallocated reserve when the canonical
    queue is not posted and the old slot has no claim, ambiguous publication,
    result, or permalink evidence.  This never repairs or republishes the
    missed slot; it only recovers its unused canonical text for a later slot.
    """
    queue_by_id = {
        str(row.get("queue_id", "")): row
        for row in queues
        if str(row.get("queue_id", ""))
        and sum(str(other.get("queue_id", "")) == str(row.get("queue_id", "")) for other in queues) == 1
    }
    posted_ids = {str(row.get("queue_id", "")) for row in posted if str(row.get("queue_id", ""))}
    releases: list[dict] = []
    for entry in entries:
        queue_id = str(entry.get("queue_id", ""))
        queue = queue_by_id.get(queue_id)
        if (not queue or str(entry.get("status", "")) != "VALIDATED"
                or str(entry.get("account_id", "")) != str(queue.get("account_id", ""))
                or not eligible_ready(queue, str(entry.get("account_id", ""))) or has_media(queue)):
            continue
        if (queue.get("business_date_jst") and queue.get("schedule_date_jst")
                and str(queue["business_date_jst"]) != str(queue["schedule_date_jst"])):
            continue
        scheduled = str(queue.get("business_date_jst") or queue.get("schedule_date_jst") or "")
        if not scheduled or scheduled >= current_business_date or queue_id in posted_ids:
            continue
        matches = [
            row for row in slot_runs
            if str(row.get("account_id", "")) == str(queue.get("account_id", ""))
            and str(row.get("slot_id", "")) == str(queue.get("slot_id", ""))
            and str(row.get("schedule_date_jst") or row.get("business_date_jst") or "") == scheduled
        ]
        if any(
            str(row.get("claim_status", "")).upper() == "CLAIMED"
            or str(row.get("status", "")).upper() in _AMBIGUOUS_SLOT_STATUSES
            or str(row.get("result_id", "")).strip()
            or str(row.get("post_url", "")).strip()
            for row in matches
        ):
            continue
        releases.append({
            "queue_id": queue_id,
            "account_id": str(queue.get("account_id", "")),
            "previous_slot_id": str(queue.get("slot_id", "")),
            "previous_business_date_jst": scheduled,
            "fields": {"slot_id": "", "business_date_jst": "", "schedule_date_jst": ""},
            "reason": "EXPIRED_UNPUBLISHED_BANK_ALLOCATION",
        })
    return releases


def release_expired_unpublished_bank_allocations(
    client,
    releases: list[dict],
    *,
    apply: bool = False,
) -> dict:
    """Persist a reviewed release batch and prove each canonical row changed.

    The batch write is intentionally not retried after an ambiguous response.
    A later run re-reads the canonical queue and can safely determine whether
    the release already happened.
    """
    if not releases:
        return {"status": "NO_EXPIRED_ALLOCATIONS", "released": 0, "would_post": False}
    if not apply:
        return {"status": "PLAN_ONLY", "released": 0, "planned": len(releases), "would_post": False}
    from gspread.utils import rowcol_to_a1
    from sheets_record_reader import records_from_values

    ws = client._ws("queue")
    read = getattr(client, "_call_with_rate_limit_retry", lambda _label, fn: fn())
    values = read("get_all_values:evergreen_release", ws.get_all_values)
    if not values:
        raise RuntimeError("EVERGREEN_QUEUE_SCHEMA_MISSING")
    headers = values[0]
    required = ("queue_id", "slot_id", "business_date_jst", "schedule_date_jst")
    if any(name not in headers for name in required):
        raise RuntimeError("EVERGREEN_QUEUE_SCHEMA_MISSING")
    queue_id_column = headers.index("queue_id")
    by_id = {
        str(row[queue_id_column]): index
        for index, row in enumerate(values[1:], start=2)
        if len(row) > queue_id_column and str(row[queue_id_column])
    }
    updates = []
    expected = {}
    for release in releases:
        row_number = by_id.get(str(release["queue_id"]))
        if not row_number:
            raise RuntimeError("EVERGREEN_RELEASE_QUEUE_MISSING")
        for field, value in release["fields"].items():
            updates.append({
                "range": rowcol_to_a1(row_number, headers.index(field) + 1),
                "values": [[value]],
            })
        expected[str(release["queue_id"])] = dict(release["fields"])
    ws.batch_update(updates, value_input_option="RAW")
    stored = records_from_values(read("get_all_values:evergreen_release:verify", ws.get_all_values))
    for queue_id, fields in expected.items():
        matches = [row for row in stored if str(row.get("queue_id", "")) == queue_id]
        if len(matches) != 1 or any(str(matches[0].get(key, "")) != value for key, value in fields.items()):
            raise RuntimeError("EVERGREEN_RELEASE_READ_AFTER_WRITE_FAILED")
    return {"status": "RELEASED", "released": len(expected), "read_after_write": "PASS", "would_post": False}


def bank_record(queue: dict, *, now: datetime, runtime_check: Callable[[dict], bool]) -> dict:
    account = str(queue.get("account_id", ""))
    if account not in policy()["accounts"] or not eligible_ready(queue, account) or has_media(queue):
        raise ValueError("EVERGREEN_CANONICAL_TEXT_REQUIRED")
    if not runtime_check(queue):
        raise ValueError("EVERGREEN_RUNTIME_GATE_REJECTED")
    text = str(queue["public_post_text"])
    exact, normalized = hashes(text)
    return {
        "fallback_id": f"evergreen_{queue['queue_id']}", "queue_id": queue["queue_id"],
        "account_id": account, "theme": queue.get("primary_topic") or queue.get("theme", ""),
        "text": text, "text_hash": exact, "normalized_hash": normalized,
        "validator_evidence_json": json.dumps({key: str(queue.get(key, "")) for key in
            ("validator_status", "internal_leak_status", "account_fit_status", "generation_policy_json")}),
        "persona_evidence_json": json.dumps({key: str(queue.get(key, "")) for key in
            ("voice_persona_status", "voice_persona_score", "semantic_voice_status", "style_fingerprint_status")}),
        "created_at": now.isoformat(), "last_used_at": "", "use_count": "0",
        "cooldown_until": "", "status": "VALIDATED",
    }


def persist_bank_record(client, queue: dict, *, now: datetime,
                        runtime_check: Callable[[dict], bool], apply: bool = False) -> dict:
    from process_threads_queue import append_row, records
    from sheets_client import TAB_DEFINITIONS

    row = bank_record(queue, now=now, runtime_check=runtime_check)
    if not apply:
        return {"status": "PLAN_ONLY", "record": row, "would_post": False}
    client._ensure_tab("evergreen_bank", TAB_DEFINITIONS["evergreen_bank"])
    existing = [r for r in records(client, "evergreen_bank") if r.get("fallback_id") == row["fallback_id"]]
    if existing:
        if len(existing) != 1 or any(str(existing[0].get(k, "")) != str(row[k]) for k in
                                    ("queue_id", "account_id", "text_hash", "normalized_hash")):
            raise RuntimeError("EVERGREEN_IDENTITY_CONFLICT")
        return {"status": "EXISTS", "fallback_id": row["fallback_id"]}
    if any(r.get("queue_id") == row["queue_id"] for r in records(client, "posted_results")):
        raise RuntimeError("EVERGREEN_ALREADY_POSTED")
    canonical = [r for r in records(client, "queue") if r.get("queue_id") == row["queue_id"]]
    if len(canonical) != 1 or bank_record(canonical[0], now=now, runtime_check=runtime_check) != row:
        raise RuntimeError("EVERGREEN_QUEUE_CHANGED")
    append_row(client, "evergreen_bank", row)
    stored = [r for r in records(client, "evergreen_bank") if r.get("fallback_id") == row["fallback_id"]]
    if len(stored) != 1 or any(str(stored[0].get(k, "")) != str(v) for k, v in row.items()):
        raise RuntimeError("EVERGREEN_READ_AFTER_WRITE_FAILED")
    return {"status": "SAVED", "fallback_id": row["fallback_id"], "read_after_write": "PASS"}


def admit_bank_batch(client, candidates: list[dict], *, now: datetime,
                     runtime_check: Callable[[dict], bool], apply: bool = False) -> dict:
    """Bounded bulk admission; ambiguous append stops and is reconciled on rerun.

    Read counts are independent of candidate count. No retry of append_rows is
    allowed after an uncertain response. All admissions preserve canonical IDs.
    """
    from gspread.utils import rowcol_to_a1
    from process_threads_queue import records
    from sheets_record_reader import records_from_values

    if len(candidates) > 30 or len({r['queue_id'] for r in candidates}) != len(candidates):
        raise ValueError("EVERGREEN_BATCH_LIMIT_OR_DUPLICATE")
    if not apply:
        return {"status": "PLAN_ONLY", "count": len(candidates), "would_post": False}
    qws, bws = client._ws("queue"), client._ws("evergreen_bank")
    qvalues, bvalues = qws.get_all_values(), bws.get_all_values()
    canonical, bank = records_from_values(qvalues), records_from_values(bvalues)
    posted_ids = {str(r.get("queue_id")) for r in records(client, "posted_results")}
    qheaders, bheaders = qvalues[0], bvalues[0]
    for name in ("queue_id", "business_date_jst", "schedule_date_jst"):
        if name not in qheaders:
            raise RuntimeError("EVERGREEN_QUEUE_SCHEMA_MISSING")
    ranges, additions, expected = [], [], []
    for candidate in candidates:
        qid = str(candidate["queue_id"])
        matches = [r for r in canonical if str(r.get("queue_id")) == qid]
        if len(matches) != 1 or qid in posted_ids:
            raise RuntimeError("EVERGREEN_CANONICAL_IDENTITY_CONFLICT")
        current = matches[0]
        before = bank_record(current, now=now, runtime_check=runtime_check)
        requested = bank_record(candidate, now=now, runtime_check=runtime_check)
        if before != requested:
            raise RuntimeError("EVERGREEN_QUEUE_CHANGED")
        allocated = {**current, "slot_id": "", "business_date_jst": "", "schedule_date_jst": ""}
        after = bank_record(allocated, now=now, runtime_check=runtime_check)
        existing = [r for r in bank if r.get("fallback_id") == after["fallback_id"]]
        if existing:
            if len(existing) != 1 or any(str(existing[0].get(k, "")) != str(after[k]) for k in
                    ("queue_id", "account_id", "text_hash", "normalized_hash", "status")):
                raise RuntimeError("EVERGREEN_BANK_IDENTITY_CONFLICT")
        else:
            if any(key not in bheaders for key in after):
                raise RuntimeError("EVERGREEN_BANK_SCHEMA_MISSING")
            additions.append(after)
        physical_row = next(i for i, row in enumerate(qvalues[1:], 2)
                            if len(row) > qheaders.index("queue_id") and str(row[qheaders.index("queue_id")]) == qid)
        for key in ("slot_id", "business_date_jst", "schedule_date_jst"):
            if current.get(key):
                ranges.append({"range": rowcol_to_a1(physical_row, qheaders.index(key) + 1), "values": [[""]]})
        expected.append((allocated, after))
    if ranges:
        qws.batch_update(ranges, value_input_option="RAW")
    if additions:
        bws.append_rows([[row.get(h, "") for h in bheaders] for row in additions], value_input_option="RAW")
    stored_q = records_from_values(qws.get_all_values())
    stored_b = records_from_values(bws.get_all_values())
    for queue, entry in expected:
        qmatches = [r for r in stored_q if r.get("queue_id") == queue["queue_id"]]
        bmatches = [r for r in stored_b if r.get("fallback_id") == entry["fallback_id"]]
        if (len(qmatches) != 1 or len(bmatches) != 1
                or any(str(qmatches[0].get(k, "")) != str(v) for k, v in queue.items())
                or any(str(bmatches[0].get(k, "")) != str(entry[k]) for k in
                       ("queue_id", "account_id", "text_hash", "normalized_hash", "status"))):
            raise RuntimeError("EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED")
    return {"status": "SAVED", "count": len(expected), "created": len(additions),
            "read_after_write": "PASS", "would_post": False}


def allocate_bank_candidate(client, *, account: str, slot: dict, now: datetime,
                            runtime_check: Callable[[dict], bool],
                            similar: Callable[[str, str], bool], apply: bool = False) -> dict:
    from process_threads_queue import records, update_row

    if slot.get("account_id", account) != account:
        raise ValueError("EVERGREEN_ACCOUNT_SLOT_MISMATCH")
    queues = records(client, "queue")
    # Allocated future candidates are reserves, not a pool to steal from.
    unallocated = [r for r in queues if not (r.get("business_date_jst") or r.get("schedule_date_jst"))]
    selected = select_evergreen(records(client, "evergreen_bank"), unallocated,
        records(client, "posted_results"), account=account, now=now,
        runtime_check=runtime_check, similar=similar)
    if not selected:
        return {"status": "NO_ELIGIBLE_EVERGREEN", "would_post": False}
    queue = selected["canonical_queue"]
    fields = {"slot_id": slot["slot_id"], "business_date_jst": slot["business_date_jst"],
              "schedule_date_jst": slot["business_date_jst"]}
    if not runtime_check({**queue, **fields}):
        return {"status": "BLOCKED", "reason": "ALLOCATION_INVALIDATES_APPROVAL", "would_post": False}
    if not apply:
        return {"status": "PLAN_ONLY", "queue_id": queue["queue_id"], "allocation": fields, "would_post": False}
    if not update_row(client, "queue", "queue_id", queue["queue_id"], fields):
        raise RuntimeError("EVERGREEN_ALLOCATION_SAVE_FAILED")
    stored = [r for r in records(client, "queue") if r.get("queue_id") == queue["queue_id"]]
    if len(stored) != 1 or any(str(stored[0].get(k, "")) != str(v) for k, v in fields.items()) or not runtime_check(stored[0]):
        raise RuntimeError("EVERGREEN_ALLOCATION_READ_AFTER_WRITE_FAILED")
    return {"status": "ALLOCATED", "queue_id": queue["queue_id"], "read_after_write": "PASS", "would_post": False}
