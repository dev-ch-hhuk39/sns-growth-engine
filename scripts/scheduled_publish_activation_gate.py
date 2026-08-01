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
    args = parser.parse_args()
    result = (
        evaluate_activation_readiness(use_sheets=args.use_sheets)
        if args.activation_readiness
        else evaluate(use_sheets=args.use_sheets)
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "ALLOW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
