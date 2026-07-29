#!/usr/bin/env python3
"""Prepare exactly the approved twelve canary queue rows; never publish."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
from build_live_canary_inventory import _rows, build_inventory
from final_production_contracts import ACCOUNTS, CANARY_TYPES
from process_threads_queue import append_row, records, resolve_queue_media, update_row
from public_post_quality import final_public_post_validator


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _field_update(candidate: dict[str, Any], kind: str) -> dict[str, Any]:
    media = kind not in {"original_text", "reference_text"}
    values = {
        "platform": "threads", "status": "READY", "public_post_text": candidate["public_post_text"],
        "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS",
        "canary_id": candidate["canary_id"], "updated_at": _now(),
    }
    if media:
        values.update({
            "source_id": candidate.get("source_id", ""), "source_post_id": candidate.get("source_post_id", ""),
            "source_video_id": candidate.get("source_video_id", ""), "clip_candidate_id": candidate.get("clip_candidate_id", ""),
            "rights_status": candidate.get("rights_status", ""), "permission_status": candidate.get("permission_status", ""),
            "media_required": "true", "media_status": "ATTACHED", "media_type": kind,
        })
        if candidate.get("media_asset_id"):
            values["media_asset_id"] = candidate["media_asset_id"]
        if candidate.get("media_url"):
            values["media_url"] = candidate["media_url"]
        if kind == "direct_carousel":
            if candidate.get("media_asset_ids"):
                values["media_asset_ids_json"] = json.dumps(candidate["media_asset_ids"])
            if candidate.get("media_urls"):
                values["media_urls_json"] = json.dumps(candidate["media_urls"])
                values["media_types_json"] = json.dumps(["image"] * len(candidate["media_urls"]))
    return values


def build_plan(datasets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    inventory = build_inventory(datasets)
    ready = {(str(row.get("account_id", "")), str(row.get("canary_type", ""))): row for row in inventory.get("canaries", []) if row.get("status") == "READY_FOR_HUMAN_CANARY"}
    candidates = {(str(row.get("account_id", "")), str(row.get("canary_type", ""))): row for row in inventory.get("candidates", [])}
    queues = {(str(row.get("account_id", "")), str(row.get("canary_id", ""))): row for row in datasets.get("queue", [])}
    rows: list[dict[str, Any]] = []
    for account_id in ACCOUNTS:
        for kind in CANARY_TYPES:
            candidate = candidates.get((account_id, kind), {})
            canary = str(candidate.get("canary_id", ""))
            existing = queues.get((account_id, canary))
            create_text_queue = existing is None and kind in {"original_text", "reference_text"} and bool(candidate)
            reasons: list[str] = []
            if (account_id, kind) not in ready or not candidate or not canary:
                reasons.append("CANARY_NOT_READY")
            if not existing and not create_text_queue:
                reasons.append("CANARY_QUEUE_MISSING")
            text = str(candidate.get("public_post_text", ""))
            if final_public_post_validator(text, account_id)["status"] != "PASS":
                reasons.append("PUBLIC_POST_VALIDATOR_BLOCKED")
            if existing and kind not in {"original_text", "reference_text"}:
                prospective = {**existing, **_field_update(candidate, kind)}
                media = resolve_queue_media(prospective)
                if not media["media_usable"]:
                    reasons.append("MEDIA_REQUIRED_MISSING")
            queue_id = str(existing.get("queue_id", "")) if existing else f"text_{canary}"
            rows.append({"canary_id": canary, "account_id": account_id, "canary_type": kind, "queue_id": queue_id, "create_text_queue": create_text_queue, "status": "READY_TO_PROMOTE" if not reasons else "BLOCKED", "reasons": reasons, "updates": _field_update(candidate, kind) if candidate else {}})
    return {"status": "PASS" if len(rows) == 12 and all(row["status"] == "READY_TO_PROMOTE" for row in rows) else "BLOCKED", "rows": rows, "would_post": False}


def apply_plan(client: Any, plan: dict[str, Any]) -> dict[str, Any]:
    if plan["status"] != "PASS":
        return {"status": "BLOCKED", "plan": plan}
    for row in plan["rows"]:
        if row.get("create_text_queue"):
            append_row(client, "queue", {"queue_id": row["queue_id"], "account_id": row["account_id"], "target_account_id": row["account_id"], "created_at": _now(), **row["updates"]})
            continue
        if not update_row(client, "queue", "queue_id", row["queue_id"], row["updates"]):
            return {"status": "PARTIAL_FAILED", "failed_queue_id": row["queue_id"], "plan": plan}
    after = records(client, "queue")
    by_id = {str(row.get("queue_id", "")): row for row in after}
    failures = [row["queue_id"] for row in plan["rows"] if str(by_id.get(row["queue_id"], {}).get("status", "")).upper() != "READY"]
    return {"status": "APPLIED" if not failures else "PARTIAL_FAILED", "queue_ids": [row["queue_id"] for row in plan["rows"]], "read_after_write": "PASS" if not failures else "FAIL", "failures": failures, "plan": plan}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-bounded-canary", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    datasets, sheets_status = _rows(True)
    plan = build_plan(datasets)
    result: dict[str, Any] = {"sheets_status": sheets_status, "plan": plan, "would_post": False}
    if args.apply:
        if not args.confirm_bounded_canary:
            result.update({"status": "BLOCKED", "reason": "--confirm-bounded-canary required"})
        else:
            from config_loader import get_config
            from sheets_client import SheetsClient
            cfg = get_config(); result.update(apply_plan(SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False), plan))
    else:
        result["status"] = "PLAN_ONLY" if plan["status"] == "PASS" else "BLOCKED"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "sheets_status": sheets_status, "would_post": False}, ensure_ascii=False))
    return 0 if result["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
