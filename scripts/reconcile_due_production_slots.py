#!/usr/bin/env python3
"""Publish buffered exact queues only; never generate content in reconciliation."""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from content_schedule import MEDIA_POST_TYPES, slot_by_id  # noqa: E402
from content_slot_runs import build_slot_run, claim_slot_run, posts_used_in_business_date, upsert_slot_run  # noqa: E402
from process_threads_queue import process_one, records, update_row  # noqa: E402
from production_inventory import JST, due_slots, eligible_ready, has_media, media_route, policy, timestamp, true  # noqa: E402
from sheets_record_reader import enable_readonly_record_cache  # noqa: E402


def enrich_posts(posts: list[dict], queues: list[dict]) -> list[dict]:
    by_id = {str(row.get("queue_id")): row for row in queues
             if sum(r.get("queue_id") == row.get("queue_id") for r in queues) == 1}
    return [{**by_id.get(str(post.get("queue_id")), {}), **post} for post in posts]


def delivery_limit(account: str, posts: list[dict], now: datetime) -> str:
    cfg = json.loads((ROOT / "config/autonomous_mode.json").read_text())
    cap, cooldown = cfg["daily_post_cap_per_account"], cfg["cooldown_minutes"]
    if account == "beauty_account":
        beauty = json.loads((ROOT / "config/beauty_account_pipeline.json").read_text())
        cap, cooldown = beauty["daily_post_cap"], beauty["cooldown_minutes"]
    if posts_used_in_business_date(account, posts, now) >= cap:
        return "DAILY_CAP_REACHED"
    for row in posts:
        if row.get("account_id") != account or not true(row.get("real_post")):
            continue
        at = timestamp(row.get("posted_at"))
        if at is None:
            return "POSTED_TIME_UNVERIFIED"
        if at + timedelta(minutes=cooldown) > now:
            return "COOLDOWN_ACTIVE"
    return ""


def candidates(queues: list[dict], slot: dict, cfg: dict, posts: list[dict] | None = None) -> list[dict]:
    selected = []
    counts: dict[str, int] = {}
    for row in queues:
        key = str(row.get("queue_id", ""))
        counts[key] = counts.get(key, 0) + 1
    media_slot = slot["post_type"] in MEDIA_POST_TYPES
    used = {str(p.get("queue_id")) for p in (posts or [])}
    for row in queues:
        if str(row.get("queue_id")) in used or counts[str(row.get("queue_id", ""))] != 1 or not eligible_ready(row, slot["account_id"]):
            continue
        media = has_media(row)
        row_date = str(row.get("business_date_jst") or row.get("schedule_date_jst") or "")
        exact_slot = row.get("slot_id") == slot["slot_id"] and row_date == slot["business_date_jst"]
        # Only unposted, same-route media can carry forward; never steal a
        # future allocation or move a text reserve from another slot.
        old_slot = slot_by_id(slot["account_id"], str(row.get("slot_id", ""))) or {}
        reusable_media = media and media_slot and (not row_date or row_date < slot["business_date_jst"]
            or (row_date == slot["business_date_jst"] and old_slot.get("review_only")))
        if not exact_slot and not reusable_media:
            continue
        if media and (not media_slot or media_route(row) != slot["post_type"]):
            continue
        if media_slot and not media and not cfg["media_shortage_text_fallback"]:
            continue
        selected.append(row)
    return sorted(selected, key=lambda row: (not has_media(row) if media_slot else False, str(row["queue_id"])))


def assigned_queue(row: dict, slot: dict) -> dict:
    return {**row, "slot_id": slot["slot_id"], "business_date_jst": slot["business_date_jst"],
            "schedule_date_jst": slot["business_date_jst"]}


def actual_route(row: dict, slot: dict) -> str:
    route = str(row.get("content_route") or row.get("generation_mode") or "")
    if has_media(row):
        return media_route(row)
    if "pdca" in route:
        return "pdca_text"
    if "reference" in route or route == "ref_score_threads":
        return "reference_text"
    return "original_text"


def verify_delivery(client, queue: dict, result: dict) -> dict:
    saved = [r for r in records(client, "posted_results") if r.get("queue_id") == queue["queue_id"]]
    stored = [r for r in records(client, "queue") if r.get("queue_id") == queue["queue_id"]]
    if len(saved) != 1 or len(stored) != 1:
        raise RuntimeError("DELIVERY_IDENTITY_UNVERIFIED")
    post = saved[0]
    if (stored[0].get("status") != "POSTED" or post.get("account_id") != queue["account_id"]
            or post.get("posted_text") != queue["public_post_text"] or not true(post.get("real_post"))
            or post.get("verification_status") != "READ_AFTER_WRITE_PASS"
            or not str(post.get("external_post_id", "")).isdigit() or not post.get("post_url")
            or (result.get("result_id") and result["result_id"] != post.get("result_id"))):
        raise RuntimeError("DELIVERY_READ_AFTER_WRITE_FAILED")
    jobs = [r for r in records(client, "metrics_collection_jobs") if r.get("result_id") == post.get("result_id")]
    if len(jobs) != 3 or {str(r.get("window_hours")) for r in jobs} != {"24", "72", "168"} or any(r.get("account_id") != queue["account_id"] for r in jobs):
        raise RuntimeError("DELIVERY_METRICS_UNVERIFIED")
    return post


def reconcile(client, *, accounts: list[str], apply: bool = False, now: datetime | None = None,
              slot_id: str = "") -> dict:
    cfg, now = policy(), now or datetime.now(JST)
    if any(account not in cfg["accounts"] for account in accounts):
        raise ValueError("UNKNOWN_ACCOUNT")
    autonomous = json.loads((ROOT / "config/autonomous_mode.json").read_text())
    if true(autonomous.get("kill_switch")) or (apply and not cfg["activation_enabled"]):
        return {"status": "BLOCKED", "reason": "KILL_SWITCH_OR_BUFFER_NOT_ACTIVATED", "would_post": False}
    outcomes = []
    for account in accounts:
        try:
            queues, posts = records(client, "queue"), records(client, "posted_results")
            due = due_slots(account, now=now, slot_runs=records(client, "content_slot_runs"),
                            posted=enrich_posts(posts, queues), recovery_minutes=cfg["recovery_window_minutes"])
            for slot in due:
                if slot_id and slot["slot_id"] != slot_id:
                    continue
                reason = delivery_limit(account, posts, now)
                if not slot["publishable"] or reason:
                    outcomes.append({**slot, "status": "BLOCKED", "reason": reason or slot["reason"]})
                    continue
                chosen = None
                snapshot = copy.copy(client)
                enable_readonly_record_cache(snapshot)
                for row in candidates(queues, slot, cfg, posts):
                    if process_one(snapshot, assigned_queue(row, slot), dry_run=True, confirm_real_post=False).get("status") == "DRY_RUN":
                        chosen = row
                        break
                if chosen is None:
                    outcomes.append({**slot, "status": "FAILED", "reason": "NO_VALIDATED_BUFFERED_QUEUE"})
                    continue
                if not apply:
                    outcomes.append({**slot, "status": "DRY_RUN", "queue_id": chosen["queue_id"], "would_post": False})
                    continue
                route = actual_route(chosen, slot)
                fallback = route != slot["post_type"]
                media_fallback = slot["post_type"] in MEDIA_POST_TYPES and not has_media(chosen)
                gate = subprocess.run([sys.executable, "scripts/scheduled_publish_activation_gate.py",
                    "--use-sheets", "--account-id", account, "--post-type", route],
                    cwd=ROOT, env={**os.environ, "PUBLISH_ENABLED": "false", "ALLOW_REAL_THREADS_POST": "false"},
                    capture_output=True, text=True, timeout=180, check=False)
                if gate.returncode:
                    outcomes.append({**slot, "status": "BLOCKED", "reason": "RUNTIME_ACTIVATION_GATE_BLOCKED"})
                    break
                claim = claim_slot_run(client, account, slot["slot_id"], at=now, schedule_date_jst=slot["business_date_jst"])
                if claim.get("status") != "CLAIMED":
                    outcomes.append({**slot, "status": "BLOCKED", "reason": claim.get("reason", "CLAIM_FAILED")})
                    break
                try:
                    fresh = [r for r in records(client, "queue") if r.get("queue_id") == chosen["queue_id"]]
                    if len(fresh) != 1 or fresh[0] != chosen:
                        raise RuntimeError("QUEUE_CHANGED_AFTER_PREFLIGHT")
                    allocation = assigned_queue(chosen, slot)
                    changed = {k: allocation[k] for k in ("slot_id", "business_date_jst", "schedule_date_jst")
                               if chosen.get(k) != allocation[k]}
                    if changed:
                        if not update_row(client, "queue", "queue_id", chosen["queue_id"], changed):
                            raise RuntimeError("ALLOCATION_SAVE_FAILED")
                        stored = [r for r in records(client, "queue") if r.get("queue_id") == chosen["queue_id"]]
                        if len(stored) != 1 or stored[0] != allocation:
                            raise RuntimeError("ALLOCATION_READ_AFTER_WRITE_FAILED")
                        chosen = stored[0]
                    if process_one(client, chosen, dry_run=True, confirm_real_post=False).get("status") != "DRY_RUN":
                        raise RuntimeError("FINAL_PREFLIGHT_FAILED")
                    result = process_one(client, chosen, dry_run=False, confirm_real_post=True)
                    if result.get("status") != "POSTED":
                        raise RuntimeError("PUBLISH_NOT_VERIFIED")
                    post = verify_delivery(client, chosen, result)
                    upsert_slot_run(client, build_slot_run(account, slot["slot_id"], now=now,
                        schedule_date_jst=slot["business_date_jst"], status="POSTED_FALLBACK" if fallback else "POSTED_PRIMARY",
                        expected_post_type=slot["post_type"], actual_generation_mode=chosen.get("generation_mode", ""),
                        delivery_engine="buffered_v1", code_revision=os.environ.get("GITHUB_SHA", ""),
                        actual_post_type="text_fallback" if media_fallback else route, fallback_level=int(fallback),
                        no_post_reason="NO_ELIGIBLE_MEDIA" if media_fallback else "PRIMARY_ROUTE_UNAVAILABLE" if fallback else "", queue_id=chosen["queue_id"],
                        result_id=post["result_id"], post_url=post["post_url"], actual_posted_at=post["posted_at"]))
                    outcomes.append({**slot, "status": "POSTED", "queue_id": chosen["queue_id"],
                                     "result_id": post["result_id"], "post_url": post["post_url"],
                                     "actual_route": route, "media_fallback": media_fallback})
                except Exception as exc:
                    upsert_slot_run(client, build_slot_run(account, slot["slot_id"], now=now,
                        schedule_date_jst=slot["business_date_jst"], status="RECOVERY_REQUIRED",
                        queue_id=chosen["queue_id"], no_post_reason=f"DELIVERY_UNVERIFIED:{type(exc).__name__}"))
                    outcomes.append({**slot, "status": "RECOVERY_REQUIRED", "queue_id": chosen["queue_id"]})
                # Never make a second attempt after any real publish invocation.
                break
        except Exception as exc:
            outcomes.append({"account_id": account, "status": "FAILED", "reason": type(exc).__name__})
    failed = any(r["status"] in {"BLOCKED", "FAILED", "RECOVERY_REQUIRED"} for r in outcomes)
    return {"status": "FAILED" if failed else "PASS", "results": outcomes, "dry_run": not apply}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", choices=["all", *policy()["accounts"]], default="all")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-reconcile", action="store_true")
    parser.add_argument("--slot-id", default="")
    args = parser.parse_args()
    if args.apply and (args.dry_run or not args.confirm_reconcile):
        parser.error("apply requires --confirm-reconcile and excludes --dry-run")
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config()
    result = reconcile(SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False),
        accounts=policy()["accounts"] if args.account_id == "all" else [args.account_id], apply=args.apply,
        slot_id=args.slot_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
