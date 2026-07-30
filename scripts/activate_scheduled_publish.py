#!/usr/bin/env python3
"""Enable scheduled publishing only after the twelve-canary evidence gate."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/autonomous_mode.json"
sys.path.insert(0, str(ROOT / "scripts"))
from scheduled_publish_activation_gate import evaluate_activation_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-scheduled-activation", action="store_true")
    args = parser.parse_args()
    gate = evaluate_activation_readiness(use_sheets=args.use_sheets)
    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", "gate": gate, "would_change": {"production_publish_activation_approved": True, "scheduled_publish_enabled": True}, "would_post": False}, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_scheduled_activation or not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-scheduled-activation --use-sheets", "gate": gate}, ensure_ascii=False)); return 1
    if gate["status"] != "ALLOW":
        print(json.dumps({"status": "BLOCKED", "reason": "twelve_canary_activation_evidence_incomplete", "gate": gate}, ensure_ascii=False)); return 1
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["production_publish_activation_approved"] = True
    config["scheduled_publish_enabled"] = True
    config["scheduled_publish_activated_at"] = datetime.now(timezone.utc).isoformat()
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "APPLIED", "gate": gate, "config_path": str(CONFIG_PATH), "would_post": False}, ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
