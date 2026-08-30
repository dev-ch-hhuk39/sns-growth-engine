#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from select_beauty_scheduled_ready import select_beauty_scheduled_ready  # noqa: E402


def row(queue_id: str, *, slot_id: str, status: str = "READY", review: str = "OK", date: str = "2026-08-26", media: bool = False, account: str = "beauty_account"):
    value = {
        "queue_id": queue_id,
        "account_id": account,
        "platform": "threads",
        "status": status,
        "slot_id": slot_id,
        "business_date_jst": date,
        "human_review_decision": review,
        "human_reviewed_at": "2026-08-26T00:00:00+00:00",
        "public_post_text": "美容の承認済み投稿です",
    }
    if media:
        value.update({
            "media_required": "true",
            "media_asset_id": f"asset_{queue_id}",
            "media_url": f"https://res.cloudinary.com/example/{queue_id}.mp4",
            "media_status": "UPLOADED",
        })
    return value


def autonomous(row_value: dict) -> dict:
    row_value.update({
        "human_review_decision": "",
        "approval_source": "autonomous_strict_beauty",
        "approval_policy": "autonomous_strict_beauty",
        "auto_publish": "true",
        "auto_ready_by": "auto_approve_queue.py",
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "semantic_voice_status": "PASS",
        "style_fingerprint_status": "VOICE_PERSONA_PASS",
    })
    return row_value


# Explicit human-approved media has priority over the text row in the same
# scheduled publication opportunity.
selected = select_beauty_scheduled_ready(
    [
        row("text", slot_id="beauty_1130"),
        row("direct", slot_id="beauty_direct_media_review", media=True),
    ],
    text_slot_id="beauty_1130",
    business_date_jst="2026-08-26",
)
assert selected and selected["queue_id"] == "direct", selected

# Strict autonomous provenance is equally valid and never impersonates a human.
selected = select_beauty_scheduled_ready(
    [autonomous(row("auto", slot_id="beauty_1130", review=""))],
    text_slot_id="beauty_1130",
    business_date_jst="2026-08-26",
)
assert selected and selected["queue_id"] == "auto", selected
assert selected["human_review_decision"] == ""

# WAITING_REVIEW or a READY row without explicit human OK is never scheduled.
selected = select_beauty_scheduled_ready(
    [
        row("waiting", slot_id="beauty_direct_media_review", status="WAITING_REVIEW", media=True),
        row("not_ok", slot_id="beauty_clip_review", review="", media=True),
        row("text", slot_id="beauty_1130"),
    ],
    text_slot_id="beauty_1130",
    business_date_jst="2026-08-26",
)
assert selected and selected["queue_id"] == "text", selected

# Media must be physically ready; a human OK alone cannot bypass media gates.
broken_media = row("broken", slot_id="beauty_direct_media_review", media=True)
broken_media["media_status"] = "PENDING"
selected = select_beauty_scheduled_ready(
    [broken_media, row("text", slot_id="beauty_1130")],
    text_slot_id="beauty_1130",
    business_date_jst="2026-08-26",
)
assert selected and selected["queue_id"] == "text", selected

# Text is bound to the current business date and exact scheduled text slot.
selected = select_beauty_scheduled_ready(
    [
        row("old", slot_id="beauty_1130", date="2026-08-25"),
        row("wrong_slot", slot_id="beauty_2030"),
    ],
    text_slot_id="beauty_1130",
    business_date_jst="2026-08-26",
)
assert selected is None, selected

# Absolute account isolation.
selected = select_beauty_scheduled_ready(
    [row("foreign", slot_id="beauty_direct_media_review", media=True, account="night_scout")],
    text_slot_id="beauty_1130",
    business_date_jst="2026-08-26",
)
assert selected is None, selected

print("PASS test_select_beauty_scheduled_ready.py")
