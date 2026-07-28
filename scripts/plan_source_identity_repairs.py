#!/usr/bin/env python3
"""Create a read-only source identity repair plan from an exported snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from source_identity_repair_contract import build_identity_repair_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", required=True, type=Path, help="Read-only JSON export")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--implementation-head", default="")
    parser.add_argument("--origin-main", default="")
    args = parser.parse_args()
    datasets = json.loads(args.datasets.read_text(encoding="utf-8"))
    if not isinstance(datasets, dict):
        raise SystemExit("datasets must be a JSON object")
    plan = build_identity_repair_plan(
        datasets,
        implementation_head=args.implementation_head,
        origin_main=args.origin_main,
    )
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"repair_plan_id": plan["repair_plan_id"], "affected_row_count": plan["affected_row_count"], "apply_allowed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
