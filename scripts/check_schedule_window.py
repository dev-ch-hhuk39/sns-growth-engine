#!/usr/bin/env python3
"""Keep delayed scheduled workflows from posting outside their JST slot."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_PATH = ROOT / "config" / "content_schedule.json"
JST = ZoneInfo("Asia/Tokyo")


def find_slot(slot_id: str) -> dict:
    schedule = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    for slots in schedule.get("accounts", {}).values():
        for slot in slots:
            if slot.get("slot_id") == slot_id:
                return slot
    raise ValueError(f"unknown_slot_id:{slot_id}")


def parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).astimezone(JST)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(JST)


def target_candidates(now_jst: datetime, target_jst: str) -> list[datetime]:
    raw_hour, minute = (int(part) for part in target_jst.split(":"))
    hour = raw_hour % 24
    return [
        datetime.combine(now_jst.date() + timedelta(days=offset), datetime.min.time(), tzinfo=JST)
        .replace(hour=hour, minute=minute)
        for offset in (-1, 0, 1)
    ]


def build_result(slot_id: str, now_utc: str | None, window_minutes: int) -> dict:
    slot = find_slot(slot_id)
    now_jst = parse_now(now_utc)
    targets = target_candidates(now_jst, str(slot["target_jst"]))
    target = min(targets, key=lambda candidate: abs(candidate - now_jst))
    delta_seconds = int((now_jst - target).total_seconds())
    in_window = abs(delta_seconds) <= window_minutes * 60
    return {
        "status": "IN_WINDOW" if in_window else "OUT_OF_WINDOW",
        "slot_id": slot_id,
        "target_jst": slot["target_jst"],
        "now_jst": now_jst.isoformat(),
        "resolved_target_jst": target.isoformat(),
        "window_minutes": window_minutes,
        "delta_seconds": delta_seconds,
        "in_window": in_window,
        "reason": "scheduled_window_open" if in_window else "scheduled_run_started_outside_allowed_window",
    }


def write_github_output(result: dict) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"in_window={'true' if result['in_window'] else 'false'}\n")
        handle.write(f"schedule_window_reason={result['reason']}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--window-minutes", type=int, default=15)
    parser.add_argument("--now-utc", help="test-only ISO timestamp")
    parser.add_argument("--write-github-output", action="store_true")
    args = parser.parse_args()
    if args.window_minutes < 0:
        parser.error("--window-minutes must be non-negative")
    result = build_result(args.slot_id, args.now_utc, args.window_minutes)
    if args.write_github_output:
        write_github_output(result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
