#!/usr/bin/env python3
"""Collect read-only, machine-readable Goal evidence without promotion.

This command never changes `docs/goal-status.json`. A human or a final
release workflow must explicitly promote evidence after validating the exact
commit, source-post bundle, and canary outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "config" / "goal_acceptance.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"value": value}
    except (OSError, json.JSONDecodeError):
        return {}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip()


def _artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False}
    raw = path.read_bytes()
    return {"present": True, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def collect(*, test_json: Path | None = None, sheets_json: Path | None = None, canary_json: Path | None = None) -> dict[str, Any]:
    acceptance = _load_json(ACCEPTANCE)
    artifacts = {
        "tests": _artifact(test_json) if test_json else {"present": False},
        "sheets": _artifact(sheets_json) if sheets_json else {"present": False},
        "canary": _artifact(canary_json) if canary_json else {"present": False},
    }
    parsed = {
        "tests": _load_json(test_json) if test_json else {},
        "sheets": _load_json(sheets_json) if sheets_json else {},
        "canary": _load_json(canary_json) if canary_json else {},
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "implementation_head": _git("rev-parse", "HEAD"),
        "origin_main": _git("rev-parse", "origin/main"),
        "promotion_required": True,
        "required_criteria": [row["id"] for row in acceptance.get("criteria", [])],
        "artifacts": artifacts,
        "machine_summary": {
            "tests_failed_count": parsed["tests"].get("failed_count"),
            "sheets_failed_checks": parsed["sheets"].get("failed_checks"),
            "canary_status": parsed["canary"].get("status"),
        },
        "candidate_status": "UNVERIFIED",
        "note": "This collector never infers PASS from prose or missing artifacts.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests-json", type=Path)
    parser.add_argument("--sheets-json", type=Path)
    parser.add_argument("--canary-json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = collect(test_json=args.tests_json, sheets_json=args.sheets_json, canary_json=args.canary_json)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
