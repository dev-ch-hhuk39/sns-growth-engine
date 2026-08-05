#!/usr/bin/env python3
"""Shared fail-closed guards for scheduled autopost execution."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
MAX_SCHEDULE_DELAY_MINUTES = int(os.environ.get("MAX_SCHEDULE_DELAY_MINUTES", "15"))

SLOT_TARGET_MINUTES_JST = {
    "ns_1400_reference": 14 * 60 + 2,
    "ns_1600_original": 16 * 60 + 2,
    "ns_1800_direct_media": 18 * 60 + 2,
    "ns_2100_clip_media": 21 * 60 + 2,
    "ns_2500_pdca": 1 * 60 + 2,
    "lm_1000_original": 10 * 60 + 4,
    "lm_1300_reference": 13 * 60 + 4,
    "lm_1600_direct_media": 16 * 60 + 4,
    "lm_1800_clip_media": 18 * 60 + 4,
    "lm_2100_pdca": 21 * 60 + 4,
}


def _summary_path() -> Path | None:
    raw = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    return Path(raw) if raw else None


def append_job_summary(title: str, payload: dict[str, Any]) -> None:
    path = _summary_path()
    if path is None:
        return
    safe_payload = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n### {title}\n\n```json\n{safe_payload}\n```\n")


def missing_required_secrets(names: tuple[str, ...] = ("GEMINI_API_KEY",)) -> list[str]:
    return [name for name in names if not os.environ.get(name, "").strip()]


def scheduled_window_decision(
    slot_id: str,
    *,
    now: datetime | None = None,
    event_name: str | None = None,
    max_delay_minutes: int = MAX_SCHEDULE_DELAY_MINUTES,
) -> dict[str, Any]:
    event = event_name if event_name is not None else os.environ.get("GITHUB_EVENT_NAME", "")
    current = (now or datetime.now(JST)).astimezone(JST)
    if event != "schedule":
        return {
            "status": "PASS",
            "reason": "not_scheduled_event",
            "slot_id": slot_id,
            "event_name": event,
            "now_jst": current.isoformat(),
        }

    target = SLOT_TARGET_MINUTES_JST.get(slot_id)
    if target is None:
        return {
            "status": "BLOCKED",
            "reason": "unknown_slot_schedule",
            "slot_id": slot_id,
            "event_name": event,
            "now_jst": current.isoformat(),
        }

    current_minutes = current.hour * 60 + current.minute
    delay = current_minutes - target
    if delay < -720:
        delay += 1440
    elif delay > 720:
        delay -= 1440

    allowed = 0 <= delay <= max_delay_minutes
    return {
        "status": "PASS" if allowed else "BLOCKED",
        "reason": "within_schedule_window" if allowed else "scheduled_run_out_of_window",
        "slot_id": slot_id,
        "event_name": event,
        "now_jst": current.isoformat(),
        "target_minute_jst": target,
        "delay_minutes": delay,
        "max_delay_minutes": max_delay_minutes,
        "publish_allowed": allowed,
    }
