#!/usr/bin/env python3
"""Fail fast when the quality-v2 rollout explicitly requires owner review.

This is a read-only local configuration check. It makes no provider calls,
does not touch Sheets, never marks a queue READY, and cannot publish.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "content_quality_v2.json"


def evaluate_policy(data: Any) -> tuple[str, int]:
    if not isinstance(data, dict) or data.get("schema_version") != "content_quality_v2":
        return "CONTENT_QUALITY_V2_POLICY_UNVERIFIED", 2
    flag = data.get("draft_only")
    if type(flag) is not bool:
        return "CONTENT_QUALITY_V2_POLICY_UNVERIFIED", 2
    if flag:
        return "OWNER_REVIEW_REQUIRED", 2
    return "QUALITY_ROLLOUT_PREFLIGHT_PASS", 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args(argv)
    try:
        if args.policy.stat().st_size > 100_000:
            raise ValueError("oversized_policy")
        data = json.loads(args.policy.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        print("[BLOCKED] CONTENT_QUALITY_V2_POLICY_UNVERIFIED")
        return 2
    code, rc = evaluate_policy(data)
    if rc:
        print("[BLOCKED] " + code)
        print("REAL_POST_ALLOWED=false; QUEUE_READY_WRITES=0; PROVIDER_CALLS=0")
    else:
        print("QUALITY_ROLLOUT_PREFLIGHT_PASS; this does not authorize publishing")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
