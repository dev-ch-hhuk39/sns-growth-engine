#!/usr/bin/env python3
"""Update the capability matrix only from explicit production evidence."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs/capability-matrix-status.json"
sys.path.insert(0, str(ROOT / "scripts"))
from final_production_contracts import ACCOUNTS, CANARY_TYPES, canary_id


def _rows_from_sheets() -> tuple[dict[str, list[dict[str, Any]]], str]:
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        tabs = ("posted_results", "metrics_collection_jobs", "metric_snapshots", "pdca_runs", "content_slot_runs")
        return {name: [dict(row) for row in client._ws(name).get_all_records()] for name in tabs}, "READ_OK"
    except Exception as exc:
        return {}, type(exc).__name__


def _verified(row: dict[str, Any]) -> bool:
    return (
        str(row.get("status", "")).upper() == "POSTED"
        and bool(str(row.get("post_url", "")).strip())
        and bool(str(row.get("external_post_id", "")).strip())
        and str(row.get("verification_status", "")).upper() in {"PASS", "VERIFIED", "READ_AFTER_WRITE_PASS"}
    )


def build_update(status: dict[str, Any], datasets: dict[str, list[dict[str, Any]]], config: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    result = json.loads(json.dumps(status))
    result["implementation_head"] = str(config.get("implementation_head", result.get("implementation_head", "")))
    posted = datasets.get("posted_results", []); jobs = datasets.get("metrics_collection_jobs", []); snapshots = datasets.get("metric_snapshots", []); pdca = datasets.get("pdca_runs", []); slots = datasets.get("content_slot_runs", [])
    changes: list[dict[str, str]] = []
    for account in ACCOUNTS:
        rows = result.setdefault("accounts", {}).setdefault(account, {})
        account_posted = [row for row in posted if str(row.get("account_id", "")) == account and _verified(row)]
        by_canary = {str(row.get("canary_id", "")): row for row in account_posted}
        for kind in CANARY_TYPES:
            row = by_canary.get(canary_id(account, kind))
            if not row:
                continue
            rows[kind] = {"state": "PASS", "evidence": {"verified_at": str(row.get("verification_checked_at") or row.get("posted_at") or now), "evidence_type": "threads_read_after_write", "evidence_ref": str(row.get("post_url"))}}
            changes.append({"account_id": account, "capability": kind, "evidence_ref": str(row.get("post_url"))})
        if account_posted:
            row = account_posted[-1]
            rows["result_persistence"] = {"state": "PASS", "evidence": {"verified_at": str(row.get("verification_checked_at") or now), "evidence_type": "posted_results_read_after_write", "evidence_ref": str(row.get("result_id", ""))}}
        measured = [row for row in snapshots if str(row.get("account_id", "")) == account and str(row.get("metrics_status", "")).upper() == "MEASURED"]
        if measured:
            row = measured[-1]; rows["metrics"] = {"state": "PASS", "evidence": {"verified_at": str(row.get("collected_at") or now), "evidence_type": "measured_metric_snapshot", "evidence_ref": str(row.get("snapshot_id", ""))}}
        account_pdca = [row for row in pdca if str(row.get("account_id", "")) == account and str(row.get("status", "")).upper() in {"COMPLETE", "APPLIED", "PLANNED"}]
        if account_pdca:
            row = account_pdca[-1]; rows["pdca"] = {"state": "PASS", "evidence": {"verified_at": str(row.get("created_at") or now), "evidence_type": "pdca_run", "evidence_ref": str(row.get("run_id", ""))}}
        persona_rows = [row for row in account_posted if str(row.get("validator_status", "")).upper() == "PASS"]
        if persona_rows:
            row = persona_rows[-1]; rows["persona"] = {"state": "PASS", "evidence": {"verified_at": str(row.get("verification_checked_at") or now), "evidence_type": "published_persona_validator", "evidence_ref": str(row.get("result_id", ""))}}
        scheduled = [row for row in slots if str(row.get("account_id", "")) == account and str(row.get("status", "")).upper() in {"POSTED_PRIMARY", "POSTED_MEDIA"}]
        if config.get("scheduled_publish_enabled") and scheduled:
            row = scheduled[-1]; rows["scheduled_publish"] = {"state": "PASS", "evidence": {"verified_at": str(row.get("actual_posted_at") or now), "evidence_type": "scheduled_slot_run", "evidence_ref": str(row.get("slot_run_id", ""))}}
    return {"status": "PLAN_ONLY", "updated_status": result, "changes": changes, "would_write": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, default=None)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-capability-update", action="store_true")
    args = parser.parse_args()
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    config = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    if args.input_json:
        datasets = json.loads(args.input_json.read_text(encoding="utf-8")); source = "INPUT_JSON"
    elif args.use_sheets:
        datasets, source = _rows_from_sheets()
    else:
        datasets, source = {}, "use_sheets_or_input_json_required"
    report = build_update(status, datasets, config); report["evidence_source"] = source
    if args.apply:
        if not args.confirm_capability_update or source != "READ_OK":
            print(json.dumps({"status": "BLOCKED", "reason": "apply requires --confirm-capability-update and live Sheets read"})); return 1
        STATUS_PATH.write_text(json.dumps(report["updated_status"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["status"] = "APPLIED"; report["would_write"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
