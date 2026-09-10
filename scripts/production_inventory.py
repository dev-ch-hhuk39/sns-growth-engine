#!/usr/bin/env python3
"""AI-free inventory planning. Approval evidence is never copied to a new ID."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from content_schedule import MEDIA_POST_TYPES, slots_for_account

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
FINAL_POST_STATUSES = {"POSTED", "POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED"}


def policy() -> dict[str, Any]:
    return json.loads((ROOT / "config/production_inventory.json").read_text())


def true(value: Any) -> bool:
    return str(value).lower() in {"true", "1", "yes"}


def timestamp(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(JST) if result.tzinfo else None
    except ValueError:
        return None


def hashes(text: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()
    return hashlib.sha256(text.encode()).hexdigest(), hashlib.sha256(normalized.encode()).hexdigest()


def scheduled_slots(account: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("aware_ordered_window_required")
    start, end = start.astimezone(JST), end.astimezone(JST)
    route_cycles = policy().get("slot_route_cycles", {}).get(account, {})
    day = start.date() - timedelta(days=1)
    result = []
    while day <= end.date():
        for slot in slots_for_account(account):
            cycle = route_cycles.get(slot["slot_id"], [])
            if cycle:
                if any(route not in MEDIA_POST_TYPES for route in cycle):
                    raise ValueError("INVALID_BUFFERED_MEDIA_ROUTE_CYCLE")
                slot = {**slot, "post_type": cycle[day.toordinal() % len(cycle)]}
            hour, minute = map(int, slot["target_jst"].split(":"))
            target = datetime.combine(day, datetime.min.time(), JST) + timedelta(hours=hour, minutes=minute)
            if start <= target < end:
                result.append({**slot, "account_id": account, "business_date_jst": day.isoformat(),
                               "target_at": target.isoformat(),
                               "allocation_key": f"{account}:{day.isoformat()}:{slot['slot_id']}"})
        day += timedelta(days=1)
    return sorted(result, key=lambda row: row["target_at"])


def has_media(row: dict[str, Any]) -> bool:
    if true(row.get("media_required")) or any(row.get(key) for key in
        ("media_asset_id", "media_url", "clip_candidate_id")):
        return True
    for key in ("media_asset_ids_json", "media_urls", "media_urls_json"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            try:
                value = json.loads(value)
            except ValueError:
                return True
        if value:
            return True
    return False


def eligible_ready(row: dict[str, Any], account: str) -> bool:
    return bool(row.get("queue_id") and str(row.get("public_post_text", "")).strip()
        and row.get("account_id") == account and row.get("target_account_id", account) in {"", account}
        and row.get("platform") == "threads" and row.get("status") == "READY"
        and not any(true(row.get(key)) for key in ("excluded_from_activation", "repost_prohibited", "superseded"))
        and all(row.get(key) == "PASS" for key in ("validator_status", "internal_leak_status", "account_fit_status")))


def media_route(row: dict[str, Any]) -> str:
    """Resolve persisted route aliases without changing signed queue fields."""
    mode = str(row.get("generation_mode") or "")
    if mode in {"saved_approved_source_clip", "approved_saved_media", "approved_source_clip"}:
        return "approved_source_clip"
    if mode in {"direct_reference_media", "saved_direct_reference_media"}:
        return "direct_reference_media"
    return ""


def coverage(queues: list[dict], *, now: datetime, settings: dict | None = None,
             runtime_check: Callable[[dict], bool]) -> list[dict]:
    cfg = settings or policy()
    result, used_ids = [], set()
    ambiguous_ids = {str(row.get("queue_id")) for row in queues
                     if sum(r.get("queue_id") == row.get("queue_id") for r in queues) != 1}
    for account in cfg["accounts"]:
        slots = scheduled_slots(account, now, now + timedelta(hours=cfg["text_horizon_hours"]))
        for slot in slots:
            if slot["post_type"] in MEDIA_POST_TYPES:
                continue
            selected, seen_hashes = [], set()
            for row in queues:
                queue_id = str(row.get("queue_id", ""))
                if queue_id in used_ids or queue_id in ambiguous_ids or not eligible_ready(row, account) or has_media(row):
                    continue
                if row.get("slot_id") != slot["slot_id"] or str(row.get("business_date_jst") or row.get("schedule_date_jst")) != slot["business_date_jst"]:
                    continue
                digest = hashes(str(row["public_post_text"]))[1]
                if digest in seen_hashes or not runtime_check(row):
                    continue
                selected.append(queue_id)
                seen_hashes.add(digest)
                used_ids.add(queue_id)
            result.append({**slot, "ready_primary": selected[:1], "ready_reserve": selected[1:],
                           "missing": max(0, cfg["text_candidates_per_slot"] - len(selected))})
    return result


def select_evergreen(entries: list[dict], queues: list[dict], posted: list[dict], *, account: str,
                     now: datetime, runtime_check: Callable[[dict], bool],
                     similar: Callable[[str, str], bool], settings: dict | None = None) -> dict | None:
    """Return a still-unused canonical queue, not forged/cloned approval evidence.

    A previously posted queue is never recycled. Reuse after cooldown requires a
    fresh queue and its own completed approval before admission to the bank.
    """
    cfg = settings or policy()
    queue_map = {str(row.get("queue_id")): row for row in queues}
    ambiguous_ids = {key for key in queue_map if sum(str(r.get("queue_id")) == key for r in queues) != 1}
    posted_ids = {str(row.get("queue_id")) for row in posted}
    recent = []
    for row in posted:
        if row.get("account_id") != account:
            continue
        at = timestamp(row.get("posted_at"))
        if at is None or at >= now - timedelta(days=cfg["recent_similarity_days"]):
            recent.append(str(row.get("posted_text", "")))
    for entry in sorted(entries, key=lambda r: (int(r.get("use_count") or 0), str(r.get("fallback_id", "")))):
        if entry.get("account_id") != account or entry.get("status") != "VALIDATED":
            continue
        queue_id = str(entry.get("queue_id", ""))
        row = queue_map.get(queue_id, {})
        if queue_id in posted_ids or queue_id in ambiguous_ids or not eligible_ready(row, account) or has_media(row):
            continue
        text = str(row["public_post_text"])
        digest, normalized = hashes(text)
        if entry.get("text_hash") != digest or entry.get("normalized_hash") != normalized:
            continue
        if entry.get("cooldown_until"):
            until = timestamp(entry["cooldown_until"])
            if until is None or until > now:
                continue
        if any(hashes(old)[1] == normalized or similar(old, text) for old in recent if old):
            continue
        if runtime_check(row):
            return {**entry, "canonical_queue": dict(row)}
    return None


def due_slots(account: str, *, now: datetime, slot_runs: list[dict], posted: list[dict],
              recovery_minutes: int = 240) -> list[dict]:
    # Terminal and ambiguous records prevent re-dispatch even if a slot row is stale.
    result = []
    for slot in scheduled_slots(account, now - timedelta(minutes=recovery_minutes), now + timedelta(microseconds=1)):
        matching = [r for r in slot_runs if r.get("account_id") == account and r.get("slot_id") == slot["slot_id"]
                    and str(r.get("schedule_date_jst") or r.get("business_date_jst")) == slot["business_date_jst"]]
        if any(r.get("status") in FINAL_POST_STATUSES for r in matching):
            continue
        matching_posts = [r for r in posted if r.get("account_id") == account and r.get("slot_id") == slot["slot_id"]
                          and str(r.get("business_date_jst") or r.get("schedule_date_jst")) == slot["business_date_jst"]]
        if any(true(r.get("real_post")) and str(r.get("external_post_id", "")).isdigit()
               and r.get("post_url") and r.get("verification_status") == "READ_AFTER_WRITE_PASS" for r in matching_posts):
            continue
        ambiguous_posts = any(true(r.get("real_post")) or r.get("external_post_id") or r.get("status") in
                              {"PUBLISH_OUTCOME_UNVERIFIED", "POSTED_SAVE_UNVERIFIED"} for r in matching_posts)
        blocked = ambiguous_posts or any(r.get("claim_status") == "CLAIMED" or r.get("status") in
                      {"RECOVERY_REQUIRED", "POSTED_SAVE_UNVERIFIED", "PUBLISH_OUTCOME_UNVERIFIED"} for r in matching)
        result.append({**slot, "publishable": not blocked, "reason": "UNVERIFIED_OR_LEASED" if blocked else "DUE"})
    return result
