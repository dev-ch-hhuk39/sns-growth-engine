#!/usr/bin/env python3
"""Update capability status only from explicit, account-scoped live evidence."""
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

from activation_route_contract import canonical_activation_type  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")

POSTED_SLOT_STATUSES = {"POSTED", "POSTED_PRIMARY", "POSTED_FALLBACK", "POSTED_MEDIA", "BACKFILLED"}


def _rows_from_sheets() -> tuple[dict[str, list[dict[str, Any]]], str]:
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from config_loader import get_config
        from sheets_client import SheetsClient

        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        tabs = ("posted_results", "metrics_collection_jobs", "metric_snapshots", "pdca_runs", "content_slot_runs")
        return {
            name: [dict(row) for row in client._ws(name).get_all_records()]
            for name in tabs
        }, "READ_OK"
    except Exception as exc:
        return {}, type(exc).__name__


def _verified(row: dict[str, Any]) -> bool:
    return (
        str(row.get("status", "")).upper() == "POSTED"
        and bool(str(row.get("post_url", "")).strip())
        and bool(str(row.get("external_post_id", "")).strip())
        and str(row.get("verification_status", "")).upper()
        in {"PASS", "VERIFIED", "READ_AFTER_WRITE_PASS"}
    )


def _evidence(kind: str, ref: str, verified_at: str, **fields: Any) -> dict[str, Any]:
    return {
        "state": "PASS",
        "evidence": {
            "verified_at": verified_at,
            "evidence_type": kind,
            "evidence_ref": ref,
            **fields,
        },
    }


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed if str(item)] if isinstance(parsed, list) else []


def _posted_capability(row: dict[str, Any]) -> str:
    media_type = str(row.get("publisher_media_type") or row.get("media_type") or "").lower()
    if media_type == "image":
        return "direct_image"
    if media_type == "carousel":
        return "direct_carousel"
    route = canonical_activation_type(
        row.get("canary_type") or row.get("content_type") or row.get("generation_mode"),
        content_route=row.get("content_route", ""),
    )
    if not route:
        canary_id = str(row.get("canary_id", "")).lower()
        route = next(
            (
                capability
                for capability in (
                    "original_text",
                    "reference_text",
                    "approved_source_clip",
                    "pdca_text",
                )
                if canary_id.endswith(f"_{capability}")
            ),
            "",
        )
    if media_type == "video":
        return "approved_source_clip" if route == "approved_source_clip" else "direct_video"
    return route if route in {"original_text", "reference_text", "approved_source_clip"} else ""


def build_update(
    status: dict[str, Any],
    datasets: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    result = json.loads(json.dumps(status))
    result["implementation_head"] = str(config.get("implementation_head", result.get("implementation_head", "")))
    posted = datasets.get("posted_results", [])
    snapshots = datasets.get("metric_snapshots", [])
    pdca = datasets.get("pdca_runs", [])
    slots = datasets.get("content_slot_runs", [])
    changes: list[dict[str, str]] = []

    for account in ACCOUNTS:
        rows = result.setdefault("accounts", {}).setdefault(account, {})
        account_posted = [row for row in posted if str(row.get("account_id", "")) == account and _verified(row)]
        for row in account_posted:
            capability = _posted_capability(row)
            if not capability or capability not in rows:
                continue
            ref = str(row.get("post_url", ""))
            rows[capability] = _evidence(
                "live_threads_api",
                ref,
                str(row.get("verification_checked_at") or row.get("posted_at") or now),
            )
            changes.append({"account_id": account, "capability": capability, "evidence_ref": ref})

        if account_posted:
            row = account_posted[-1]
            rows["result_persistence"] = _evidence(
                "live_sheets",
                str(row.get("result_id", "")),
                str(row.get("verification_checked_at") or now),
            )
            persona_rows = [item for item in account_posted if str(item.get("validator_status", "")).upper() == "PASS"]
            if persona_rows:
                item = persona_rows[-1]
                rows["persona"] = _evidence(
                    "live_sheets",
                    str(item.get("result_id", "")),
                    str(item.get("verification_checked_at") or now),
                )

        measured = [
            row for row in snapshots
            if str(row.get("account_id", "")) == account
            and str(row.get("metrics_status", "")).upper() == "MEASURED"
        ]
        if measured:
            row = measured[-1]
            rows["metrics"] = _evidence(
                "live_metrics",
                str(row.get("snapshot_id", "")),
                str(row.get("collected_at") or now),
            )
        windows_by_result: dict[str, dict[int, dict[str, Any]]] = {}
        for row in measured:
            try:
                window = int(row.get("collection_window_hours", 0))
            except (TypeError, ValueError):
                continue
            result_id = str(row.get("result_id", ""))
            if result_id and window in {24, 72, 168}:
                windows_by_result.setdefault(result_id, {})[window] = row
        complete_metrics = next(
            ((rid, values) for rid, values in windows_by_result.items() if {24, 72, 168}.issubset(values)),
            None,
        )
        if complete_metrics:
            result_id, windows = complete_metrics
            rows["metrics_24_72_168"] = _evidence(
                "live_metrics",
                result_id,
                max(str(item.get("collected_at") or now) for item in windows.values()),
                metric_windows={
                    str(window): {"status": "MEASURED", "snapshot_id": str(item.get("snapshot_id", ""))}
                    for window, item in windows.items()
                },
            )

        account_pdca = [
            row for row in pdca
            if str(row.get("account_id", "")) == account
            and str(row.get("metrics_status", "")).upper() == "MEASURED_ONLY"
            and _json_list(row.get("metric_input_refs_json"))
        ]
        if account_pdca:
            row = account_pdca[-1]
            refs = _json_list(row.get("metric_input_refs_json"))
            rows["pdca"] = _evidence("live_metrics", str(row.get("run_id", "")), str(row.get("created_at") or now))
            rows["pdca_measured_feedback"] = _evidence(
                "live_metrics",
                str(row.get("run_id", "")),
                str(row.get("created_at") or now),
                metric_input_refs=refs,
            )

        scheduled = sorted(
            [
                row for row in slots
                if str(row.get("account_id", "")) == account
                and str(row.get("event_name", "")) == "schedule"
            ],
            key=lambda row: str(row.get("actual_started_at") or row.get("created_at") or ""),
        )
        posted_scheduled = [row for row in scheduled if str(row.get("status", "")).upper() in POSTED_SLOT_STATUSES]
        if config.get("scheduled_publish_enabled") and posted_scheduled:
            row = posted_scheduled[-1]
            rows["scheduled_publish"] = _evidence(
                "live_schedule",
                str(row.get("workflow_run_id") or row.get("slot_run_id", "")),
                str(row.get("actual_posted_at") or now),
            )
        last_three = scheduled[-3:]
        if len(last_three) == 3 and all(
            str(row.get("status", "")).upper() in POSTED_SLOT_STATUSES
            and str(row.get("workflow_run_id", "")).strip()
            for row in last_three
        ):
            rows["scheduled_publish_streak"] = _evidence(
                "live_schedule",
                str(last_three[-1].get("workflow_run_id", "")),
                str(last_three[-1].get("actual_posted_at") or now),
                schedule_runs=[
                    {
                        "event_name": "schedule",
                        "run_id": str(row.get("workflow_run_id", "")),
                        "slot_run_id": str(row.get("slot_run_id", "")),
                    }
                    for row in last_three
                ],
            )
        recovered = [
            row for row in posted_scheduled
            if str(row.get("status", "")).upper() == "POSTED_FALLBACK"
            or int(str(row.get("fallback_level") or "0")) > 0
        ]
        if recovered:
            row = recovered[-1]
            recovery = _evidence(
                "live_schedule",
                str(row.get("workflow_run_id") or row.get("slot_run_id", "")),
                str(row.get("actual_posted_at") or now),
            )
            rows["ready_inventory_recovery"] = recovery
            rows["failure_recovery"] = json.loads(json.dumps(recovery))

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
        datasets = json.loads(args.input_json.read_text(encoding="utf-8"))
        source = "INPUT_JSON"
    elif args.use_sheets:
        datasets, source = _rows_from_sheets()
    else:
        datasets, source = {}, "use_sheets_or_input_json_required"
    report = build_update(status, datasets, config)
    report["evidence_source"] = source
    if args.apply:
        if not args.confirm_capability_update or source != "READ_OK":
            print(json.dumps({"status": "BLOCKED", "reason": "apply requires --confirm-capability-update and live Sheets read"}))
            return 1
        STATUS_PATH.write_text(json.dumps(report["updated_status"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["status"] = "APPLIED"
        report["would_write"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
