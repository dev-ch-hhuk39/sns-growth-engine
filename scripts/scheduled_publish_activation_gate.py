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
from validate_production_activation import _live_rows
from final_production_contracts import activation_evidence


def _decision(
    config: dict[str, Any],
    posted: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    *,
    evidence_source: str,
    require_persisted_activation: bool,
) -> dict[str, Any]:
    evidence = activation_evidence(posted, jobs)
    reasons: list[str] = []
    if config.get("kill_switch"):
        reasons.append("kill_switch_enabled")
    if evidence.get("status") != "READY_FOR_ACTIVATION":
        reasons.append("twelve_canary_activation_evidence_incomplete")
    if require_persisted_activation:
        if not config.get("production_publish_activation_approved"):
            reasons.append("production_publish_activation_not_approved")
        if not config.get("scheduled_publish_enabled"):
            reasons.append("scheduled_publish_not_enabled")
    return {
        "status": "ALLOW" if not reasons else "BLOCKED",
        "mode": "RUNTIME" if require_persisted_activation else "ACTIVATION_READINESS",
        "evidence_source": evidence_source,
        "activation_evidence": evidence,
        "blocked_reasons": reasons,
        "would_post": False,
    }


def evaluate(*, use_sheets: bool) -> dict[str, Any]:
    """Runtime gate: evidence and both persisted activation flags are required."""
    config = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    posted, jobs, source = _live_rows(use_sheets)
    return _decision(
        config,
        posted,
        jobs,
        evidence_source=source,
        require_persisted_activation=True,
    )


def evaluate_activation_readiness(*, use_sheets: bool) -> dict[str, Any]:
    """Pre-activation gate: do not require flags that this action will set."""
    config = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    posted, jobs, source = _live_rows(use_sheets)
    return _decision(
        config,
        posted,
        jobs,
        evidence_source=source,
        require_persisted_activation=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--activation-readiness", action="store_true")
    args = parser.parse_args()
    result = evaluate_activation_readiness(use_sheets=args.use_sheets) if args.activation_readiness else evaluate(use_sheets=args.use_sheets)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "ALLOW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
