#!/usr/bin/env python3
"""Read real inventory and delivery evidence; absence is never a successful SLO."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from content_schedule import MEDIA_POST_TYPES  # noqa: E402
from hybrid_ai_gate import hybrid_ai_gate_passed  # noqa: E402
from hybrid_ai_source_context import build_source_context  # noqa: E402
from production_inventory import JST, coverage, due_slots, eligible_ready, has_media, media_asset_ids, media_route, policy, recently_used_media_asset_ids, select_evergreen  # noqa: E402
from reconcile_due_production_slots import delivery_limit, enrich_posts  # noqa: E402
from generate_threads_ideas_from_references import original_text_similarity_guard  # noqa: E402
from public_post_quality import final_public_post_validator  # noqa: E402
from sheets_record_reader import enable_readonly_record_cache, read_records_safely  # noqa: E402


def post_evidence_counts(posts, jobs):
    seen, duplicates, unverified, missing_metrics = set(), 0, 0, 0
    for post in posts:
        key = (post.get("account_id"), str(post.get("external_post_id", "")))
        if key in seen:
            duplicates += 1
        seen.add(key)
        if not key[1].isdigit() or not post.get("post_url") or post.get("verification_status") != "READ_AFTER_WRITE_PASS":
            unverified += 1
        matched = [row for row in jobs if row.get("result_id") == post.get("result_id")
                   and row.get("account_id") == post.get("account_id")]
        if len(matched) != 3 or {str(row.get("window_hours")) for row in matched} != {"24", "72", "168"}:
            missing_metrics += 1
    return {"duplicate_posts": duplicates, "unverified_posts": unverified, "metrics_missing": missing_metrics}


def buffered_run_verified(run, posts):
    trigger = str(run.get("execution_trigger", ""))
    execution_evidence = (
        trigger == "xserver_cron" and bool(run.get("host_execution_id"))
    ) or (
        trigger == "github_schedule_recovery" and bool(run.get("workflow_run_id"))
    )
    return (
        run.get("delivery_engine") == "buffered_v1"
        and len(str(run.get("code_revision", ""))) == 40
        and run.get("status") in {"POSTED_PRIMARY", "POSTED_FALLBACK"}
        and execution_evidence
        and any(post.get("result_id") == run.get("result_id")
                and post.get("verification_status") == "READ_AFTER_WRITE_PASS" for post in posts)
    )


def effective_due_slots(account, due, posts, now):
    """Do not call a deliberately cap-suppressed slot an outage."""
    if due and delivery_limit(account, posts, now) == "DAILY_CAP_REACHED":
        return [], due
    return due, []


def text_ready_coverage(rows):
    """Measure text inventory independently from media-guaranteed slots."""
    text_rows = [row for row in rows if row.get("post_type") not in MEDIA_POST_TYPES]
    covered = sum(not row.get("missing", 0) for row in text_rows)
    return covered, len(text_rows)


def publisher_usable_media_ids(rows, *, account, route, publisher_check, posted=None, now=None):
    """Count distinct assets that pass the actual publisher's read-only gate.

    Media V1 soft quality warnings remain warnings. Rights, provenance,
    technical, account, duplicate, and other publisher hard gates are applied
    by ``process_one(..., dry_run=True)`` and are the acceptance authority.
    """
    usable = set()
    recent_assets = recently_used_media_asset_ids(
        posted or [], account=account, now=now or datetime.now(JST)
    )
    for row in rows:
        if (not eligible_ready(row, account) or not has_media(row)
                or media_route(row) != route):
            continue
        if media_asset_ids(row) & recent_assets:
            continue
        result = publisher_check(row)
        if result.get("status") != "DRY_RUN":
            continue
        identity = str(row.get("media_asset_id") or row.get("clip_candidate_id") or "")
        if identity:
            usable.add(identity)
    return usable


def evaluate(client, *, now=None):
    now = now or datetime.now(JST)
    cfg, blockers, resource_constraints = policy(), [], []
    enable_readonly_record_cache(client)
    tables = {}
    for name in ("queue", "posted_results", "content_slot_runs", "metrics_collection_jobs", "evergreen_bank"):
        try:
            tables[name] = read_records_safely(client, name)
        except Exception as exc:
            tables[name] = []
            blockers.append(f"SHEETS_READ_FAILED:{name}:{type(exc).__name__}")

    def check(row):
        public = final_public_post_validator(str(row.get("public_post_text", "")), str(row.get("account_id")))
        return public.get("status") == "PASS" and hybrid_ai_gate_passed(row, build_source_context(client, row))[0]

    queue = tables["queue"]
    rows = coverage(
        queue, now=now, settings=cfg, runtime_check=check,
        evergreen_entries=tables["evergreen_bank"], posted=tables["posted_results"],
        similar=lambda a, b: original_text_similarity_guard(a, b)["status"] == "BLOCKED",
        include_media_fallback=True,
    )
    text_covered, text_total = text_ready_coverage(rows)
    bank_counts, media_counts, accounts = {}, {}, {}
    for account in cfg["accounts"]:
        usable_bank = set()
        for entry in tables["evergreen_bank"]:
            candidate = select_evergreen([entry], [r for r in queue if not (r.get("business_date_jst") or r.get("schedule_date_jst"))],
                tables["posted_results"], account=account, now=now, runtime_check=check,
                similar=lambda a, b: original_text_similarity_guard(a, b)["status"] == "BLOCKED", settings=cfg)
            if candidate:
                usable_bank.add(candidate["normalized_hash"])
        bank_counts[account] = len(usable_bank)
        from process_threads_queue import process_one
        media_counts[account] = {}
        scheduled_media_routes = {
            str(row.get("post_type", ""))
            for row in rows
            if row.get("account_id") == account
            and row.get("post_type") in MEDIA_POST_TYPES
        }
        for route in sorted(scheduled_media_routes):
            valid_ids = set()
            valid_ids = publisher_usable_media_ids(
                queue,
                account=account,
                route=route,
                publisher_check=lambda row: process_one(
                    client, row, dry_run=True, confirm_real_post=False
                ),
                posted=tables["posted_results"],
                now=now,
            )
            media_counts[account][route] = len(valid_ids)
        enriched_posts = enrich_posts(tables["posted_results"], queue)
        due = due_slots(account, now=now, slot_runs=tables["content_slot_runs"],
                        posted=enriched_posts, recovery_minutes=cfg["recovery_window_minutes"])
        due, cap_suppressed = effective_due_slots(account, due, enriched_posts, now)
        account_rows = [row for row in rows if row["account_id"] == account]
        accounts[account] = {
            "unresolved_due_slots": due,
            "cap_suppressed_due_slots": cap_suppressed,
            "text_slots": sum(row["post_type"] not in MEDIA_POST_TYPES for row in account_rows),
            "media_slots": sum(row["post_type"] in MEDIA_POST_TYPES for row in account_rows),
            "media_slot_text_fallbacks": sum(row.get("actual_coverage_type") == "text_fallback" for row in account_rows),
        }
        if bank_counts[account] < cfg["minimum_evergreen_per_account"]:
            blockers.append(f"EVERGREEN_LOW:{account}")
        for route, count in media_counts[account].items():
            if count < cfg["minimum_media_per_route"]:
                shortage = f"MEDIA_LOW:{account}:{route}"
                resource_constraints.append(shortage)
                blockers.append(shortage)
        fallback_count = accounts[account]["media_slot_text_fallbacks"]
        if fallback_count:
            blockers.append(f"MEDIA_TEXT_FALLBACK:{account}:{fallback_count}")
    posts = [p for p in tables["posted_results"] if p.get("account_id") in cfg["accounts"]
             and str(p.get("real_post", "")).lower() == "true"]
    buffered_result_ids = {str(run.get("result_id", "")) for run in tables["content_slot_runs"]
                           if run.get("delivery_engine") == "buffered_v1" and run.get("result_id")}
    buffered_posts = [post for post in posts if str(post.get("result_id", "")) in buffered_result_ids]
    legacy_posts = [post for post in posts if str(post.get("result_id", "")) not in buffered_result_ids]
    current_evidence = post_evidence_counts(buffered_posts, tables["metrics_collection_jobs"])
    legacy_evidence = post_evidence_counts(legacy_posts, tables["metrics_collection_jobs"])
    duplicates = current_evidence["duplicate_posts"]
    unverified = current_evidence["unverified_posts"]
    missing_metrics = current_evidence["metrics_missing"]
    unresolved = sum(len(a["unresolved_due_slots"]) for a in accounts.values())
    if text_covered != text_total or not text_total:
        blockers.append("READY_COVERAGE_INCOMPLETE")
    for name, count in (("DUPLICATE_POSTS", duplicates), ("UNVERIFIED_POSTS", unverified),
                        ("METRICS_MISSING", missing_metrics), ("UNRESOLVED_DUE_SLOTS", unresolved)):
        if count:
            blockers.append(f"{name}:{count}")
    if cfg["scheduler_primary"] not in {"github_actions_reconciler", "external"}:
        blockers.append("SCHEDULER_UNCONFIGURED")
    elif cfg["scheduler_primary"] == "external" and not cfg["external_scheduler_verified"]:
        blockers.append("EXTERNAL_SCHEDULER_UNVERIFIED")
    reconciler_verified = bool(cfg["activation_enabled"]) and all(any(
        run.get("account_id") == account and buffered_run_verified(run, posts)
        for run in tables["content_slot_runs"]) for account in cfg["accounts"])
    if not reconciler_verified:
        blockers.append("BUFFERED_RECONCILER_UNVERIFIED")
    if not posts:
        blockers.append("PRODUCTION_DELIVERY_EVIDENCE_MISSING")
    return {"development_complete": not blockers, "production_autonomous": not blockers,
            "scheduler": {"primary": cfg["scheduler_primary"], "reconciler": reconciler_verified},
            "text_ready_horizon_hours": cfg["text_horizon_hours"],
            "text_ready_coverage": text_covered / text_total if text_total else 0,
            "text_ready_slots": text_total,
            "text_ready_slots_covered": text_covered,
            "text_slots": rows, "fallback_bank": bank_counts, "media_ready_reserve": media_counts,
            "media_counts_provisional": False, "resource_constraints": resource_constraints,
            "legacy_audit": {"post_count": len(legacy_posts), **legacy_evidence},
            "accounts": accounts, "unresolved_due_slots": unresolved,
            "duplicate_posts": duplicates, "unverified_posts": unverified, "metrics_missing": missing_metrics,
            "blockers": blockers, "would_post": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config()
    result = evaluate(SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if not result["blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
