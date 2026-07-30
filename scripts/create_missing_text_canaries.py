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
from generation_quality_gates import evaluate_generation_quality, persisted_quality_evidence

TARGETS = (("night_scout", "original_text"), ("night_scout", "reference_text"), ("liver_manager", "original_text"), ("liver_manager", "reference_text"))


def build_rows(
    existing: list[dict[str, Any]],
    posted_results: list[dict[str, Any]] | None = None,
    *,
    targets: tuple[tuple[str, str], ...] = TARGETS,
    batch_id: str = "",
    seed_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    existing_canaries = {str(row.get("canary_id", "")) for row in existing}
    rows: list[dict[str, Any]] = []; skipped: list[str] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    batch = batch_id or f"fresh_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    posted = list(posted_results or [])
    pending = [row for row in existing if str(row.get("status", "")).upper() in {"READY", "WAITING_REVIEW", "PROCESSING"}]

    def row_text(row: dict[str, Any]) -> str:
        return str(row.get("posted_text") or row.get("public_post_text") or row.get("text") or "")
    accepted: list[dict[str, Any]] = [dict(row) for row in (seed_candidates or [])]
    for account_id, generation_mode in targets:
        canary = f"canary_{batch}_{account_id}_{generation_mode}"
        if canary in existing_canaries:
            skipped.append(canary); continue
        generated = None
        novelty = None
        quality = None
        validation = None
        attempt_evidence: list[dict[str, Any]] = []
        selected_attempt = 0
        for attempt in range(5):
            excluded_topics = [
                str(row.get("primary_topic", ""))
                for row in accepted
                if str(row.get("account_id", "")) == account_id
            ]
            generated = generate_production_post(
                account_id,
                batch_id=batch,
                content_type=generation_mode,
                recent_posts=[row_text(row) for row in posted if row_text(row)],
                attempt=attempt,
                excluded_topics=excluded_topics,
            )
            text = str(generated.get("public_post_text", ""))
            if "GENERATION_PROVIDER_UNAVAILABLE" in generated.get("blocked_reasons", []):
                return {"status": "BLOCKED", "reason": "GENERATION_PROVIDER_UNAVAILABLE", "canary_id": canary}
            novelty = evaluate_candidate_novelty(account_id=account_id, public_post_text=text, recent_posts=posted, pending_queue=pending)
            primary_topic = str(generated.get("grounding_summary", {}).get("quality_topic", ""))
            structure_variant = generated.get("grounding_summary", {}).get("structure_variant", "")
            quality = evaluate_generation_quality(
                account_id,
                text,
                pending + accepted,
                batch_compared=accepted,
                structure_variant=structure_variant,
                primary_topic=primary_topic,
            )
            validation = final_public_post_validator(text, account_id=account_id)
            attempt_evidence.append({
                "attempt": attempt + 1,
                "primary_topic": quality.get("primary_topic", ""),
                "public_post_text": text,
                "novelty_status": novelty.get("status", ""),
                "quality_status": quality.get("status", ""),
                "validation_status": validation.get("status", ""),
                "validation_blocked_reasons": validation.get("blocked_reasons", []),
                "diversity_blocked_reasons": quality.get("diversity_blocked_reasons", []),
                "topic_blocked_reasons": quality.get("topic_blocked_reasons", []),
            })
            if novelty["status"] == "PASS" and quality["status"] == "PASS" and validation["status"] == "PASS":
                selected_attempt = attempt + 1
                break
        if selected_attempt == 0:
            if not generated or not novelty or novelty.get("status") != "PASS":
                return {"status": "NOVELTY_EXHAUSTED", "canary_id": canary, "novelty": novelty or {}, "attempt_evidence": attempt_evidence}
            if not quality or quality.get("status") != "PASS":
                return {"status": "QUALITY_EXHAUSTED", "canary_id": canary, "quality": quality or {}, "attempt_evidence": attempt_evidence}
            return {"status": "VALIDATION_EXHAUSTED", "canary_id": canary, "validation": validation or {}, "attempt_evidence": attempt_evidence}
        assert validation is not None
        design = dict(generated.get("post_design") or {})
        quality_evidence = persisted_quality_evidence(quality)
        row = {"queue_id": f"text_{canary}", "batch_id": batch, "account_id": account_id, "target_account_id": account_id, "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": generation_mode, "public_post_text": text, "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS", "public_post_quality_score": validation["public_post_quality_score"], "reader_value_score": validation["reader_value_score"], "naturalness_score": validation["naturalness_score"], "cta_pressure_score": validation["cta_pressure_score"], "content_hash": novelty["text_hash"], "recent_post_similarity": novelty["recent_semantic_similarity"], "caption_provider": generated["generation_provider"], "caption_provider_version": generated["generation_provider_version"], "generation_attempt": selected_attempt, "generation_rule_version": generated.get("generation_rule_version", ""), "generation_policy_json": json.dumps(generated.get("generation_policy", {}), ensure_ascii=False), "feature_schema_version": generated.get("feature_schema_version", ""), "hook_text": design.get("hook_text", ""), "body_text": design.get("body_text", ""), "closing_text": design.get("closing_text", ""), "cta_intent": design.get("cta_intent", ""), "key_claims_json": json.dumps(design.get("key_claims", []), ensure_ascii=False), "post_design_json": json.dumps(design, ensure_ascii=False), "canary_id": canary, "created_at": now, "updated_at": now, **quality_evidence}
        rows.append(row); accepted.append(row)
    return {"status": "PLAN_ONLY", "rows": rows, "skipped_existing": skipped, "would_post": False}


def _append(client: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Idempotently append exact text candidates and verify every queue id."""
    from sheets_client import TAB_DEFINITIONS
    client._ensure_tab("queue", TAB_DEFINITIONS["queue"])
    ws = client._ws("queue"); headers = ws.row_values(1)
    before = {str(row.get("queue_id", "")) for row in ws.get_all_records()}
    pending = [row for row in rows if str(row.get("queue_id", "")) not in before]
    if pending:
        ws.append_rows([[str(row.get(header, "")) for header in headers] for row in pending], value_input_option="USER_ENTERED")
    after = {str(row.get("queue_id", "")) for row in ws.get_all_records()}
    expected = [str(row["queue_id"]) for row in rows]
    missing = [queue_id for queue_id in expected if queue_id not in after]
    return {
        "status": "APPLIED" if not missing else "PARTIAL_FAILURE",
        "created_queue_ids": [str(row["queue_id"]) for row in pending],
        "skipped_existing_queue_ids": sorted(set(expected) & before),
        "read_after_write": {"expected_queue_ids": expected, "missing_queue_ids": missing},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-text-canaries", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--targets", default="", help="comma-separated account_id:content_type values; default is the full fresh text set")
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
    targets = TARGETS
    if args.targets:
        parsed = []
        for value in args.targets.split(","):
            account_id, separator, content_type = value.strip().partition(":")
            if not separator or (account_id, content_type) not in TARGETS:
                print(json.dumps({"status": "BLOCKED", "reason": "invalid_target", "would_post": False})); return 1
            parsed.append((account_id, content_type))
        targets = tuple(parsed)
    result = build_rows(existing, posted_results, targets=targets)
    if args.apply:
        if not args.confirm_text_canaries:
            result = {"status": "BLOCKED", "reason": "--apply requires --confirm-text-canaries", "would_post": False}
        elif result["status"] == "PLAN_ONLY":
            result.update(_append(client, result.pop("rows")))
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
