#!/usr/bin/env python3
"""Canonical account-scoped content slots and fallbacks for production runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_FILE = ROOT / "config/content_schedule.json"
TEXT_POST_TYPES = {"original_text", "reference_text", "pdca_text"}
MEDIA_POST_TYPES = {"direct_reference_media", "generated_clip_media"}
POST_TYPES = TEXT_POST_TYPES | MEDIA_POST_TYPES
EXPECTED_SLOTS_PER_ACCOUNT = 5


def load_content_schedule() -> dict[str, Any]:
    return json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))


def slots_for_account(account_id: str) -> list[dict[str, Any]]:
    return list(load_content_schedule().get("accounts", {}).get(account_id, []))


def slot_by_id(account_id: str, slot_id: str) -> dict[str, Any] | None:
    for slot in slots_for_account(account_id):
        if slot.get("slot_id") == slot_id:
            return dict(slot)
    return None


def slot_by_cron(account_id: str, cron: str) -> dict[str, Any] | None:
    for slot in slots_for_account(account_id):
        if slot.get("cron_utc") == cron:
            return dict(slot)
    return None


def text_slots(account_id: str) -> list[dict[str, Any]]:
    return [slot for slot in slots_for_account(account_id) if slot.get("post_type") in TEXT_POST_TYPES]


def media_slots(account_id: str) -> list[dict[str, Any]]:
    return [slot for slot in slots_for_account(account_id) if slot.get("post_type") in MEDIA_POST_TYPES]


def validate_schedule() -> list[str]:
    errors: list[str] = []
    data = load_content_schedule()
    for account_id, slots in data.get("accounts", {}).items():
        ids = [str(slot.get("slot_id", "")) for slot in slots]
        crons = [str(slot.get("cron_utc", "")) for slot in slots]
        if len(ids) != len(set(ids)):
            errors.append(f"{account_id}:duplicate_slot_id")
        if any(not value for value in ids + crons):
            errors.append(f"{account_id}:missing_slot_id_or_cron")
        if len(slots) != EXPECTED_SLOTS_PER_ACCOUNT:
            errors.append(f"{account_id}:expected_{EXPECTED_SLOTS_PER_ACCOUNT}_slots")
        types = {str(slot.get("post_type", "")) for slot in slots}
        missing_types = POST_TYPES - types
        if missing_types:
            errors.append(f"{account_id}:missing_post_types={','.join(sorted(missing_types))}")
        for slot in slots:
            if slot.get("post_type") not in POST_TYPES:
                errors.append(f"{account_id}:{slot.get('slot_id', 'unknown')}:unknown_post_type")
            if "fallback_chain" not in slot:
                errors.append(f"{account_id}:{slot.get('slot_id', 'unknown')}:fallback_chain_missing")
    return errors
