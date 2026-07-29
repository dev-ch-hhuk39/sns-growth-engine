#!/usr/bin/env python3
"""Return success only when a scheduled media publish is fully activated."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_production_activation import _live_rows
from final_production_contracts import activation_evidence


def evaluate(*, use_sheets: bool) -> dict[str, object]:
    config = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    posted, jobs, source = _live_rows(use_sheets)
    evidence = activation_evidence(posted, jobs)
    allowed = bool(
        not config.get("kill_switch")
        and config.get("production_publish_activation_approved")
        and config.get("scheduled_publish_enabled")
        and evidence.get("status") == "READY_FOR_ACTIVATION"
    )
    return {"status": "ALLOW" if allowed else "BLOCKED", "evidence_source": source, "activation_evidence": evidence, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args(); result = evaluate(use_sheets=args.use_sheets)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "ALLOW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
