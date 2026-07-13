#!/usr/bin/env python3
"""Canonical, account-scoped content slots for autonomous workflows.

The schedule is data rather than duplicated workflow lore.  A text worker may
only run a text-capable slot; a media worker owns the media slot.  This keeps a
single account from racing itself or consuming a daily cap twice.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_FILE = ROOT / "config/content_schedule.json"
TEXT_POST_TYPES = {"reference_based_text", "original_hypothesis", "pdca_repost_variant"}
MEDIA_POST_TYPES = {"approved_clip_candidate", "saved_media_post"}


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
    return errors
