#!/usr/bin/env python3
"""Find overdue unfilled slots; optionally fill each once via the safe fallback."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
from config_loader import get_config  # noqa: E402
from content_schedule import load_content_schedule  # noqa: E402
from content_slot_runs import business_date, existing_slot_row  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402

JST = timezone(timedelta(hours=9))
POSTED = {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED"}
PUBLISH_SUCCEEDED = {"POSTED", "POSTED_SAVE_FAILED"}
MEDIA_POST_ENV = (
    "PUBLISH_ENABLED",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
)


def _true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _media_post_gates_enabled() -> bool:
    return all(_true(os.environ.get(name)) for name in MEDIA_POST_ENV)


def missing_slots(client: SheetsClient, account_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
    local = (now or datetime.now(JST)).astimezone(JST)
    operational_day = datetime.fromisoformat(business_date(local)).date()
    result = []
    for slot in load_content_schedule()["accounts"].get(account_id, []):
        configured_hour, minute = map(int, slot["target_jst"].split(":"))
        target_day = operational_day + timedelta(days=1 if configured_hour >= 24 else 0)
        target = datetime(target_day.year, target_day.month, target_day.day, configured_hour % 24, minute, tzinfo=JST)
        if target > local - timedelta(minutes=20):
            continue
        existing = existing_slot_row(client, account_id, slot["slot_id"], local) or {}
        status = str(existing.get("status", ""))
        expiry = str(existing.get("lease_expires_at", ""))
        if str(existing.get("claim_status", "")) == "CLAIMED" and expiry:
            try:
                if datetime.fromisoformat(expiry).astimezone(JST) > local:
                    continue
            except ValueError:
                continue
        if status not in POSTED:
            result.append({"slot_id": slot["slot_id"], "expected_post_type": slot["post_type"], "status": status or "MISSING", "target_jst": target.isoformat()})
    return sorted(result, key=lambda row: row["target_jst"])


def _text_fallback(
    client: SheetsClient,
    account_id: str,
    slot: dict[str, Any],
    *,
    apply: bool,
    reason: str,
) -> dict[str, Any]:
    from run_slot_text_fallback import build_plan, execute

    plan = build_plan(account_id, str(slot["slot_id"]), reason, apply=apply)
    if not apply:
        return {
            "status": "PLAN_ONLY",
            "path": "text_fallback",
            "reason": reason,
            "actual_post_type": plan.get("actual_post_type", ""),
        }
    result = execute(plan, client)
    return {
        "status": result.get("status", "FAILED"),
        "path": "text_fallback",
        "reason": reason,
        "actual_post_type": plan.get("actual_post_type", ""),
    }


def recover_slot(
    client: SheetsClient,
    account_id: str,
    slot: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Recover READY media first; use text only when no valid media exists."""
    slot_id = str(slot["slot_id"])
    expected = str(slot.get("expected_post_type", ""))

    if expected == "direct_reference_media":
        from run_direct_reference_media_pipeline import dispatch_ready

        preflight = dispatch_ready(client, account_id, slot_id, dry_run=True)
        if preflight.get("status") == "DRY_RUN":
            if not apply:
                return {
                    "status": "PLAN_ONLY",
                    "path": "saved_direct_reference_media",
                    "selected_queue_id": preflight.get("selected_queue_id", ""),
                }
            if not _media_post_gates_enabled():
                return {
                    "status": "BLOCKED_MEDIA_GATE",
                    "path": "saved_direct_reference_media",
                    "reason": "ready_media_exists_but_media_post_gates_are_disabled",
                }
            posted = dispatch_ready(client, account_id, slot_id, dry_run=False)
            return {
                "status": posted.get("status", "FAILED"),
                "path": "saved_direct_reference_media",
                "selected_queue_id": posted.get("selected_queue_id", ""),
                "post_url": (posted.get("post_result") or {}).get("post_url", ""),
            }
        return _text_fallback(
            client,
            account_id,
            slot,
            apply=apply,
            reason=f"direct_media_recovery_{str(preflight.get('reason') or preflight.get('status') or 'unavailable').lower()}",
        )

    if expected == "generated_clip_media":
        from run_media_production_pipeline import build_plan as build_media_plan, execute as execute_media

        media_plan = build_media_plan(
            apply=False,
            confirm=False,
            client=client,
            account_id=account_id,
            post_saved_media=True,
            slot_id=slot_id,
        )
        if media_plan.get("selected_clip_candidate_id") and not media_plan.get("blocked_reasons"):
            if not apply:
                return {
                    "status": "PLAN_ONLY",
                    "path": "saved_generated_clip_media",
                    "selected_clip_candidate_id": media_plan.get("selected_clip_candidate_id", ""),
                }
            if not _media_post_gates_enabled():
                return {
                    "status": "BLOCKED_MEDIA_GATE",
                    "path": "saved_generated_clip_media",
                    "reason": "ready_media_exists_but_media_post_gates_are_disabled",
                }
            apply_plan = build_media_plan(
                apply=True,
                confirm=True,
                client=client,
                account_id=account_id,
                post_saved_media=True,
                slot_id=slot_id,
            )
            posted = execute_media(apply_plan, client)
            return {
                "status": posted.get("status", "FAILED"),
                "path": "saved_generated_clip_media",
                "selected_clip_candidate_id": posted.get("selected_clip_candidate_id", ""),
                "post_url": (posted.get("post_result") or {}).get("post_url", ""),
            }
        reason = "generated_clip_recovery_" + str(
            (media_plan.get("blocked_reasons") or [media_plan.get("status", "unavailable")])[0]
        ).lower()
        return _text_fallback(client, account_id, slot, apply=apply, reason=reason)

    return _text_fallback(client, account_id, slot, apply=apply, reason="missed_text_slot_aftercare")


def main() -> int:
    parser = argparse.ArgumentParser(description="detect and one-time backfill missed content slots")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-backfill", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_backfill:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-backfill"})); return 1
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    accounts = ["night_scout", "liver_manager"] if args.account_id == "all" else [args.account_id]
    plans = {account: missing_slots(client, account) for account in accounts}
    result: dict[str, Any] = {"status": "PLAN_ONLY", "aftercare_threshold_minutes": 20, "missing_slots": plans, "would_post": False, "backfills": []}
    if not args.apply:
        for account, slots in plans.items():
            if slots:
                result["backfills"].append({"account_id": account, "slot_id": slots[0]["slot_id"], **recover_slot(client, account, slots[0], apply=False)})
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if str(os.environ.get("PUBLISH_ENABLED", "")).lower() not in {"1", "true", "yes"} or str(os.environ.get("ALLOW_REAL_THREADS_POST", "")).lower() not in {"1", "true", "yes"}:
        print(json.dumps({**result, "status": "BLOCKED", "reason": "Threads publishing gates are required"}, ensure_ascii=False, indent=2)); return 1
    # One late post per account/run; every posting path re-checks slot claims.
    for account, slots in plans.items():
        if not slots:
            continue
        slot = slots[0]
        recovery = recover_slot(client, account, slot, apply=True)
        result["backfills"].append({"account_id": account, "slot_id": slot["slot_id"], **recovery})
    result["status"] = "BACKFILLED" if any(row.get("status") in PUBLISH_SUCCEEDED for row in result["backfills"]) else "NO_POST"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
