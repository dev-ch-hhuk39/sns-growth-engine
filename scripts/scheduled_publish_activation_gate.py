#!/usr/bin/env python3
"""Evaluate evidence readiness and the persisted scheduled-publish switch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from final_production_contracts import activation_evidence

from activation_integrity import (
    evaluate_canary_integrity,
    load_activation_datasets,
)


def _decision(
    config: dict[str, Any],
    posted: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    *,
    evidence_source: str,
    require_persisted_activation: bool,
    canary_integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = activation_evidence(
        posted,
        jobs,
        canary_integrity=canary_integrity,
    )

    reasons: list[str] = []

    if config.get("kill_switch"):
        reasons.append("kill_switch_enabled")

    evidence_is_live = evidence_source == "READ_OK"

    if not evidence_is_live:
        reasons.append("production_evidence_source_not_live")

    if canary_integrity is not None and canary_integrity.get("status") != "PASS":
        reasons.append("canary_source_integrity_incomplete")

    if evidence.get("DELIVERY_READY") != "YES":
        reasons.append("delivery_evidence_incomplete")

    if evidence.get("CONTENT_READY") != "YES":
        reasons.append("content_evidence_incomplete")

    if require_persisted_activation:
        if not config.get("production_publish_activation_approved"):
            reasons.append("production_publish_activation_not_approved")

        if not config.get("scheduled_publish_enabled"):
            reasons.append("scheduled_publish_not_enabled")

        if config.get("pre_activation_queue_archive_required") and not config.get("pre_activation_queue_archive_completed"):
            reasons.append("pre_activation_queue_archive_not_completed")

    reasons = list(dict.fromkeys(reasons))

    allowed = not reasons

    return {
        "status": ("ALLOW" if allowed else "BLOCKED"),
        "mode": ("RUNTIME" if require_persisted_activation else "ACTIVATION_READINESS"),
        "evidence_source": evidence_source,
        "DELIVERY_READY": (
            "YES" if (evidence_is_live and evidence.get("DELIVERY_READY") == "YES") else "NO"
        ),
        "CONTENT_READY": (
            "YES" if (evidence_is_live and evidence.get("CONTENT_READY") == "YES") else "NO"
        ),
        "AUTONOMOUS_PRODUCTION_READY": (
            "YES" if (allowed and require_persisted_activation) else "NO"
        ),
        "SCHEDULED_PUBLISH": (
            "ON"
            if (
                allowed and require_persisted_activation and config.get("scheduled_publish_enabled")
            )
            else "OFF"
        ),
        "activation_evidence": evidence,
        "canary_source_integrity": (canary_integrity or {"status": "NOT_EVALUATED"}),
        "blocked_reasons": reasons,
        "would_post": False,
    }


def evaluate(
    *,
    use_sheets: bool,
) -> dict[str, Any]:
    """Runtime gate requiring integrity, evidence, and persisted flags."""

    config = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))

    datasets, source = load_activation_datasets(use_sheets)

    integrity = evaluate_canary_integrity(datasets)

    return _decision(
        config,
        datasets["posted_results"],
        datasets["metrics_collection_jobs"],
        evidence_source=source,
        require_persisted_activation=True,
        canary_integrity=integrity,
    )


def _route_slot(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("account_id", "")).strip(),
        str(row.get("canary_type") or row.get("content_route") or row.get("content_type") or "").strip(),
    )


def _scoped_text_decision(
    config: dict[str, Any],
    posted: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    *,
    evidence_source: str,
    canary_integrity: dict[str, Any],
    account_id: str,
    post_type: str,
) -> dict[str, Any]:
    """Require live activation evidence for one scheduled text route only."""
    target = (account_id, post_type)
    reasons: list[str] = []
    if config.get("kill_switch"):
        reasons.append("kill_switch_enabled")
    if evidence_source != "READ_OK":
        reasons.append("production_evidence_source_not_live")
    if not config.get("production_publish_activation_approved"):
        reasons.append("production_publish_activation_not_approved")
    if not config.get("scheduled_publish_enabled"):
        reasons.append("scheduled_publish_not_enabled")
    if config.get("pre_activation_queue_archive_required") and not config.get("pre_activation_queue_archive_completed"):
        reasons.append("pre_activation_queue_archive_not_completed")

    integrity_checks = [row for row in canary_integrity.get("checks", []) if _route_slot(row) == target]
    integrity_pass = any(str(row.get("status", "")).upper() == "PASS" for row in integrity_checks)
    if not integrity_pass:
        reasons.append("scoped_canary_source_integrity_incomplete")

    verified: list[str] = []
    for row in posted:
        if _route_slot(row) != target or row.get("excluded_from_activation") in {True, "true", "TRUE", "1"}:
            continue
        canary_id = str(row.get("canary_id", "")).strip()
        if (
            canary_id
            and str(row.get("status", "")).upper() == "POSTED"
            and str(row.get("post_url", "")).strip()
            and str(row.get("external_post_id", "")).strip()
            and str(row.get("verification_status", "")).upper() in {"PASS", "VERIFIED", "READ_AFTER_WRITE_PASS"}
        ):
            verified.append(canary_id)
    verified = list(dict.fromkeys(verified))
    if not verified:
        reasons.append("scoped_posted_read_after_write_missing")

    windows_by_canary: dict[str, set[int]] = {}
    for row in jobs:
        canary_id = str(row.get("canary_id", "")).strip()
        if not canary_id or str(row.get("status", "")).upper() in {"CANCELLED", "FAILED"}:
            continue
        try:
            window = int(row.get("window_hours", 0))
        except (TypeError, ValueError):
            continue
        windows_by_canary.setdefault(canary_id, set()).add(window)
    selected = next((value for value in reversed(verified) if {24, 72, 168} <= windows_by_canary.get(value, set())), "")
    if verified and not selected:
        reasons.append("scoped_metrics_windows_incomplete")

    reasons = list(dict.fromkeys(reasons))
    allowed = not reasons
    return {
        "status": "ALLOW" if allowed else "BLOCKED",
        "mode": "RUNTIME_SCOPED_TEXT",
        "scope": {"account_id": account_id, "post_type": post_type},
        "evidence_source": evidence_source,
        "DELIVERY_READY": "YES" if integrity_pass and bool(verified) else "NO",
        "CONTENT_READY": "YES" if selected else "NO",
        "AUTONOMOUS_PRODUCTION_READY": "YES" if allowed else "NO",
        "SCHEDULED_PUBLISH": "ON" if allowed else "OFF",
        "selected_evidence_canary_id": selected,
        "required_metric_windows": [24, 72, 168],
        "blocked_reasons": reasons,
        "would_post": False,
    }


def evaluate_scoped_text(*, use_sheets: bool, account_id: str, post_type: str) -> dict[str, Any]:
    config = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    datasets, source = load_activation_datasets(use_sheets)
    integrity = evaluate_canary_integrity(datasets)
    return _scoped_text_decision(
        config,
        datasets["posted_results"],
        datasets["metrics_collection_jobs"],
        evidence_source=source,
        canary_integrity=integrity,
        account_id=account_id,
        post_type=post_type,
    )


def evaluate_activation_readiness(
    *,
    use_sheets: bool,
) -> dict[str, Any]:
    """Pre-activation gate requiring live evidence and source integrity."""

    config = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))

    datasets, source = load_activation_datasets(use_sheets)

    integrity = evaluate_canary_integrity(datasets)

    return _decision(
        config,
        datasets["posted_results"],
        datasets["metrics_collection_jobs"],
        evidence_source=source,
        require_persisted_activation=False,
        canary_integrity=integrity,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--activation-readiness", action="store_true")
    parser.add_argument("--account-id", choices=["night_scout", "liver_manager"])
    parser.add_argument("--post-type", choices=["original_text", "reference_text", "pdca_text"])
    args = parser.parse_args()
    if bool(args.account_id) != bool(args.post_type):
        parser.error("--account-id and --post-type must be provided together")
    result = (
        evaluate_scoped_text(use_sheets=args.use_sheets, account_id=args.account_id, post_type=args.post_type)
        if args.account_id
        else
        evaluate_activation_readiness(use_sheets=args.use_sheets)
        if args.activation_readiness
        else evaluate(use_sheets=args.use_sheets)
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "ALLOW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
