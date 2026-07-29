#!/usr/bin/env python3
"""Produce one redacted, read-only JSON readiness report for final activation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_media_permissions import build_report as permission_report
from build_live_canary_inventory import _rows, build_inventory
from final_production_contracts import activation_evidence, canary_required_permission_deficits, canary_source_integrity_report, source_integrity_report
from quarantine_stale_operational_rows import RULES, build_plan as stale_plan


def _config(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def build_report(*, use_sheets: bool) -> dict[str, Any]:
    datasets, sheets_status = _rows(use_sheets)
    parents = datasets.get("source_posts", []); children = datasets.get("source_post_media", [])
    operational = {key: [] for key in RULES}
    if use_sheets and sheets_status == "READ_OK":
        try:
            sys.path.insert(0, str(ROOT / "src"))
            from config_loader import get_config
            from sheets_client import SheetsClient
            cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
            operational = {key: [dict(row) for row in client._ws(key).get_all_records()] for key in RULES}
        except Exception:
            pass
    activation = {**activation_evidence(datasets.get("posted_results", []), []), "evidence_source": "DATASET_PARTIAL"}
    # build_live_canary_inventory intentionally reads only its dedicated tabs;
    # include posted/metric evidence if those extra rows are available later.
    if use_sheets and sheets_status == "READ_OK":
        try:
            sys.path.insert(0, str(ROOT / "src"))
            from config_loader import get_config
            from sheets_client import SheetsClient
            cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
            posted = [dict(row) for row in client._ws("posted_results").get_all_records()]
            jobs = [dict(row) for row in client._ws("metrics_collection_jobs").get_all_records()]
            activation = {**activation_evidence(posted, jobs), "evidence_source": "READ_OK"}
        except Exception as exc:
            activation = {"status": "BLOCKED", "reason": type(exc).__name__, "evidence_source": "SCHEMA_MISSING" if type(exc).__name__ == "WorksheetNotFound" else type(exc).__name__}
    auto = _config("config/autonomous_mode.json")
    media = _config("config/media_growth_engine.json")
    inventory = build_inventory(datasets)
    source_integrity = source_integrity_report(parents, children)
    canary_integrity = canary_source_integrity_report(datasets, inventory.get("candidates", []))
    selected_parent_ids = {str(item.get("source_post_id", "")) for item in inventory.get("candidates", []) if str(item.get("source_post_id", ""))}
    historical_failures = [item for item in source_integrity.get("failures", []) if str(item.get("source_post_id", "")) not in selected_parent_ids]
    return {
        "status": "READY" if activation.get("status") == "READY_FOR_ACTIVATION" else "NOT_READY",
        "sheets_status": sheets_status,
        "source_read_after_write": source_integrity,
        "canary_source_integrity": canary_integrity,
        "quarantine_candidates_excluding_canary": {
            "status": "PLAN_ONLY",
            "count": len(historical_failures),
            "source_post_ids": sorted({str(item.get("source_post_id", "")) for item in historical_failures if str(item.get("source_post_id", ""))})[:100],
        },
        "stale_operational_rows": stale_plan(operational, older_than_minutes=120),
        "permission_audit": permission_report(use_sheets=use_sheets),
        "canary_required_permission_deficits": canary_required_permission_deficits(datasets.get("media_permissions", [])),
        "canary_inventory": inventory,
        "activation_guard": activation,
        "safety": {
            "kill_switch": bool(auto.get("kill_switch")),
            "production_publish_activation_approved": bool(auto.get("production_publish_activation_approved")),
            "scheduled_publish_enabled": bool(auto.get("scheduled_publish_enabled")),
            "media_posts_enabled": bool(auto.get("allow_media_posts")),
            "media_schedule_configured": bool(media.get("media_schedule_enabled")),
            "x_optional": True,
        },
        "would_fetch": False, "would_write": False, "would_post": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(); report = build_report(use_sheets=args.use_sheets)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); report["output_path"] = str(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2)); return 0 if report["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
