#!/usr/bin/env python3
"""Verify a separately approved source identity repair snapshot; never apply it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from source_identity_repair_contract import verify_identity_repair_outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-plan", required=True, type=Path)
    parser.add_argument("--after-datasets", required=True, type=Path, help="Read-only JSON export after human-approved repair")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    plan = json.loads(args.repair_plan.read_text(encoding="utf-8"))
    datasets = json.loads(args.after_datasets.read_text(encoding="utf-8"))
    result = verify_identity_repair_outcome(plan, datasets)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"repair_plan_id": result["repair_plan_id"], "status": result["status"], "affected_row_count": result["affected_row_count"]}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
