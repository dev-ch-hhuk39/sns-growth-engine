#!/usr/bin/env python3
"""Select one strictly approved Beauty READY row for a scheduled publish slot.

The two existing Beauty publish windows remain the only autonomous Beauty
publication opportunities.  A human-approved media row may occupy a window;
otherwise the current date's approved text row for that window is used.
Nothing in this selector mutates Sheets or publishes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402

BEAUTY_ACCOUNT = "beauty_account"
MEDIA_SLOTS = {
    "beauty_direct_media_review",
    "beauty_clip_review",
}
MEDIA_OK_STATUSES = {"ATTACHED", "UPLOADED"}
AUTONOMOUS_APPROVAL_SOURCE = "autonomous_strict_beauty"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return _text(value).lower() in {"1", "true", "yes"}


def _sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        _text(row.get("human_reviewed_at") or row.get("created_at") or row.get("updated_at")),
        _text(row.get("queue_id")),
    )


def _approval_source(row: dict[str, Any]) -> str:
    if _text(row.get("human_review_decision")).upper() == "OK":
        return "human_review"
    if (
        _text(row.get("approval_source")) == AUTONOMOUS_APPROVAL_SOURCE
        and _text(row.get("approval_policy")) == AUTONOMOUS_APPROVAL_SOURCE
        and _truthy(row.get("auto_publish"))
        and _text(row.get("auto_ready_by"))
        and _text(row.get("validator_status")).upper() == "PASS"
        and _text(row.get("internal_leak_status")).upper() == "PASS"
        and _text(row.get("account_fit_status")).upper() == "PASS"
        and _text(row.get("semantic_voice_status")).upper() == "PASS"
        and _text(row.get("style_fingerprint_status")).upper() in {"PASS", "VOICE_PERSONA_PASS"}
    ):
        return AUTONOMOUS_APPROVAL_SOURCE
    return ""


def select_beauty_scheduled_ready(
    rows: list[dict[str, Any]],
    *,
    text_slot_id: str,
    business_date_jst: str,
) -> dict[str, Any] | None:
    """Prefer approved media inventory, then today's approved text slot."""

    media: list[dict[str, Any]] = []
    text_rows: list[dict[str, Any]] = []

    for raw in rows:
        row = dict(raw)
        if _text(row.get("account_id")) != BEAUTY_ACCOUNT:
            continue
        if _text(row.get("platform")).lower() != "threads":
            continue
        if _text(row.get("status")).upper() != "READY":
            continue
        if _truthy(row.get("excluded_from_activation")):
            continue

        # READY alone is not enough.  The row needs either a real human OK or
        # the formal strict-automation provenance; the latter never writes a
        # fake human_review_decision.
        if not _approval_source(row):
            continue

        slot_id = _text(row.get("slot_id"))
        if slot_id in MEDIA_SLOTS:
            if not _truthy(row.get("media_required")):
                continue
            if not _text(row.get("media_asset_id")) or not _text(row.get("media_url")):
                continue
            if _text(row.get("media_status")).upper() not in MEDIA_OK_STATUSES:
                continue
            media.append(row)
            continue

        if slot_id != text_slot_id:
            continue
        if _text(row.get("business_date_jst")) != business_date_jst:
            continue
        text_rows.append(row)

    # Giving the oldest strictly approved media row first prevents inventory
    # from being stranded while preserving the same two daily windows.
    if media:
        return sorted(media, key=_sort_key)[0]
    if text_rows:
        return sorted(text_rows, key=_sort_key)[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--business-date-jst", required=True)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    if args.slot_id not in {"beauty_1130", "beauty_2030"}:
        raise SystemExit("[BLOCKED] unsupported Beauty scheduled text slot")
    if not args.use_sheets:
        raise SystemExit("[BLOCKED] production selector requires --use-sheets")

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    rows = read_records_safely(client, "queue")
    selected = select_beauty_scheduled_ready(
        [dict(row) for row in rows],
        text_slot_id=args.slot_id,
        business_date_jst=args.business_date_jst,
    )
    queue_id = _text((selected or {}).get("queue_id"))
    selected_slot_id = _text((selected or {}).get("slot_id"))
    route = _text(
        (selected or {}).get("content_route")
        or (selected or {}).get("generation_mode")
        or (selected or {}).get("content_type")
    )
    approval_source = _approval_source(selected or {})
    approved = bool(queue_id and approval_source)
    human_approved = approval_source == "human_review"

    payload = {
        "status": "SELECTED" if queue_id else "NO_READY_QUEUE",
        "account_id": BEAUTY_ACCOUNT,
        "scheduled_text_slot_id": args.slot_id,
        "business_date_jst": args.business_date_jst,
        "selected_queue_id": queue_id,
        "selected_slot_id": selected_slot_id,
        "selected_route": route,
        "approved": approved,
        "approval_source": approval_source,
        "human_approved": human_approved,
    }
    print(json.dumps(payload, ensure_ascii=False))

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"queue_id={queue_id}\n")
            handle.write(f"selected_slot_id={selected_slot_id}\n")
            handle.write(f"selected_route={route}\n")
            handle.write(f"approved={'true' if approved else 'false'}\n")
            handle.write(f"approval_source={approval_source}\n")
            handle.write(f"human_approved={'true' if human_approved else 'false'}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
