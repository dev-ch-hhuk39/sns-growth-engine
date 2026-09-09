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
from production_inventory import JST, coverage, due_slots, eligible_ready, has_media, media_route, policy, select_evergreen  # noqa: E402
from reconcile_due_production_slots import enrich_posts  # noqa: E402
from generate_threads_ideas_from_references import original_text_similarity_guard  # noqa: E402
from public_post_quality import final_public_post_validator  # noqa: E402
from sheets_record_reader import enable_readonly_record_cache, read_records_safely  # noqa: E402


def evaluate(client, *, now=None):
    now = now or datetime.now(JST)
    cfg, blockers = policy(), []
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
    rows = coverage(queue, now=now, settings=cfg, runtime_check=check)
    covered = sum(not r["missing"] for r in rows)
    bank_counts, media_counts, accounts = {}, {}, {}
    for account in cfg["accounts"]:
        approved = {r["queue_id"] for r in queue if eligible_ready(r, account) and check(r)}
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
        for route in sorted(MEDIA_POST_TYPES):
            valid_ids = set()
            for row in queue:
                if row.get("queue_id") in approved and has_media(row) and media_route(row) == route:
                    if process_one(client, row, dry_run=True, confirm_real_post=False).get("status") == "DRY_RUN":
                        valid_ids.add(row["queue_id"])
            media_counts[account][route] = len(valid_ids)
        due = due_slots(account, now=now, slot_runs=tables["content_slot_runs"],
                        posted=enrich_posts(tables["posted_results"], queue), recovery_minutes=cfg["recovery_window_minutes"])
        accounts[account] = {"unresolved_due_slots": due}
        if bank_counts[account] < cfg["minimum_evergreen_per_account"]:
            blockers.append(f"EVERGREEN_LOW:{account}")
        for route, count in media_counts[account].items():
            if count < cfg["minimum_media_per_route"]:
                blockers.append(f"MEDIA_LOW:{account}:{route}")
    posts = [p for p in tables["posted_results"] if p.get("account_id") in cfg["accounts"]
             and str(p.get("real_post", "")).lower() == "true"]
    seen, duplicates, unverified, missing_metrics = set(), 0, 0, 0
    for post in posts:
        key = (post.get("account_id"), str(post.get("external_post_id", "")))
        if key in seen:
            duplicates += 1
        seen.add(key)
        if not key[1].isdigit() or not post.get("post_url") or post.get("verification_status") != "READ_AFTER_WRITE_PASS":
            unverified += 1
        jobs = [r for r in tables["metrics_collection_jobs"] if r.get("result_id") == post.get("result_id")
                and r.get("account_id") == post.get("account_id")]
        if len(jobs) != 3 or {str(j.get("window_hours")) for j in jobs} != {"24", "72", "168"}:
            missing_metrics += 1
    unresolved = sum(len(a["unresolved_due_slots"]) for a in accounts.values())
    if covered != len(rows) or not rows:
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
        r.get("account_id") == account and r.get("workflow_name") == "Content Slot Recovery"
        and r.get("delivery_engine") == "buffered_v1" and len(str(r.get("code_revision", ""))) == 40
        and r.get("workflow_run_id") and r.get("status") in {"POSTED_PRIMARY", "POSTED_FALLBACK"}
        and any(p.get("result_id") == r.get("result_id") and p.get("verification_status") == "READ_AFTER_WRITE_PASS" for p in posts)
        for r in tables["content_slot_runs"]) for account in cfg["accounts"])
    if not reconciler_verified:
        blockers.append("BUFFERED_RECONCILER_UNVERIFIED")
    if not posts:
        blockers.append("PRODUCTION_DELIVERY_EVIDENCE_MISSING")
    return {"development_complete": not blockers, "production_autonomous": not blockers,
            "scheduler": {"primary": cfg["scheduler_primary"], "reconciler": reconciler_verified},
            "text_ready_horizon_hours": cfg["text_horizon_hours"],
            "text_ready_coverage": covered / len(rows) if rows else 0,
            "text_slots": rows, "fallback_bank": bank_counts, "media_ready_reserve": media_counts,
            "media_counts_provisional": False, "accounts": accounts, "unresolved_due_slots": unresolved,
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
