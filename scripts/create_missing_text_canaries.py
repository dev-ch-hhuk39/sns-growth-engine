#!/usr/bin/env python3
"""Create the three missing text canary queue rows; never publish them."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from public_post_quality import final_public_post_validator, generate_production_post
from production_novelty import evaluate_candidate_novelty

TARGETS = (("night_scout", "original_text"), ("night_scout", "reference_text"), ("liver_manager", "original_text"), ("liver_manager", "reference_text"))


def build_rows(existing: list[dict[str, Any]], posted_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    existing_canaries = {str(row.get("canary_id", "")) for row in existing}
    rows: list[dict[str, Any]] = []; skipped: list[str] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    batch = f"fresh_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    posted = list(posted_results or [])
    pending = [row for row in existing if str(row.get("status", "")).upper() in {"READY", "WAITING_REVIEW", "PROCESSING"}]
    for account_id, generation_mode in TARGETS:
        canary = f"canary_{batch}_{account_id}_{generation_mode}"
        if canary in existing_canaries:
            skipped.append(canary); continue
        generated = None
        novelty = None
        for attempt in range(5):
            generated = generate_production_post(account_id, batch_id=batch, content_type=generation_mode, recent_posts=[str(row.get("posted_text", "")) for row in posted], attempt=attempt)
            text = str(generated.get("public_post_text", ""))
            if "GENERATION_PROVIDER_UNAVAILABLE" in generated.get("blocked_reasons", []):
                return {"status": "BLOCKED", "reason": "GENERATION_PROVIDER_UNAVAILABLE", "canary_id": canary}
            novelty = evaluate_candidate_novelty(account_id=account_id, public_post_text=text, recent_posts=posted, pending_queue=pending)
            if novelty["status"] == "PASS":
                break
        if not generated or not novelty or novelty["status"] != "PASS":
            return {"status": "NOVELTY_EXHAUSTED", "canary_id": canary, "novelty": novelty or {}}
        validation = final_public_post_validator(text, account_id=account_id)
        if validation["status"] != "PASS":
            return {"status": "BLOCKED", "reason": "generated_text_failed_validator", "canary_id": canary, "validation": validation}
        rows.append({"queue_id": f"text_{canary}", "account_id": account_id, "target_account_id": account_id, "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": generation_mode, "public_post_text": text, "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS", "public_post_quality_score": validation["public_post_quality_score"], "reader_value_score": validation["reader_value_score"], "naturalness_score": validation["naturalness_score"], "cta_pressure_score": validation["cta_pressure_score"], "content_hash": novelty["text_hash"], "recent_post_similarity": novelty["recent_semantic_similarity"], "caption_provider": generated["generation_provider"], "caption_provider_version": generated["generation_provider_version"], "canary_id": canary, "created_at": now, "updated_at": now})
    return {"status": "PLAN_ONLY", "rows": rows, "skipped_existing": skipped, "would_post": False}


def _append(client: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    from sheets_client import TAB_DEFINITIONS
    client._ensure_tab("queue", TAB_DEFINITIONS["queue"])
    ws = client._ws("queue"); headers = ws.row_values(1)
    if rows: ws.append_rows([[str(row.get(header, "")) for header in headers] for row in rows], value_input_option="USER_ENTERED")
    after = ws.get_all_records(); ids = {str(row.get("queue_id", "")) for row in after}
    missing = [str(row["queue_id"]) for row in rows if str(row["queue_id"]) not in ids]
    return {"status": "APPLIED" if not missing else "PARTIAL_FAILURE", "read_after_write": {"expected_queue_ids": [row["queue_id"] for row in rows], "missing_queue_ids": missing}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-text-canaries", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "reason": "--use-sheets is required", "would_post": False})); return 1
    sys.path.insert(0, str(ROOT / "src")); from config_loader import get_config; from sheets_client import SheetsClient, TAB_DEFINITIONS
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
    if args.apply: client._ensure_tab("queue", TAB_DEFINITIONS["queue"])
    try: existing = client._ws("queue").get_all_records()
    except Exception: existing = []
    try:
        client._ensure_tab("posted_results", TAB_DEFINITIONS["posted_results"])
        posted_results = client._ws("posted_results").get_all_records()
    except Exception:
        posted_results = []
    result = build_rows(existing, posted_results)
    if args.apply:
        if not args.confirm_text_canaries:
            result = {"status": "BLOCKED", "reason": "--apply requires --confirm-text-canaries", "would_post": False}
        elif result["status"] == "PLAN_ONLY":
            result.update(_append(client, result.pop("rows")))
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
