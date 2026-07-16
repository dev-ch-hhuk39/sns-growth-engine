#!/usr/bin/env python3
"""Bounded cleanup for dedicated transient media directories."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/media_growth_engine.json"


def build_cleanup_plan(
    now_timestamp: float | None = None,
    *,
    delete_roots: list[Path] | None = None,
    audit_root: Path | None = None,
    config: dict | None = None,
) -> dict:
    now = now_timestamp or datetime.now(timezone.utc).timestamp()
    limits = (config or json.loads(CONFIG.read_text(encoding="utf-8"))).get("resource_limits", {})
    failed_days = int(limits.get("failed_media_retention_days", 7))
    audit_days = int(limits.get("processed_asset_audit_days", 30))
    delete_roots = delete_roots or [ROOT / "output/direct_media", ROOT / "output/downloads"]
    audit_root = audit_root or ROOT / "output/clips"
    delete_candidates = []
    audit_candidates = []
    for base in delete_roots:
        if not base.exists():
            continue
        for root, _, files in os.walk(base):
            for name in files:
                path = Path(root) / name
                try:
                    age_days = (now - path.stat().st_mtime) / 86400
                except OSError:
                    continue
                if age_days >= failed_days:
                    delete_candidates.append({"path": str(path), "age_days": round(age_days, 1), "bytes": path.stat().st_size})
    if audit_root.exists():
        for root, _, files in os.walk(audit_root):
            for name in files:
                path = Path(root) / name
                try:
                    age_days = (now - path.stat().st_mtime) / 86400
                except OSError:
                    continue
                if age_days >= audit_days:
                    audit_candidates.append({"path": str(path), "age_days": round(age_days, 1), "bytes": path.stat().st_size})
    return {
        "status": "PLAN_ONLY",
        "delete_candidate_count": len(delete_candidates),
        "delete_candidate_bytes": sum(row["bytes"] for row in delete_candidates),
        "audit_candidate_count": len(audit_candidates),
        "delete_candidates": delete_candidates,
        "audit_candidates": audit_candidates,
        "processed_assets_auto_deleted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="clean dedicated media workspace")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-cleanup", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_cleanup:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-cleanup"}))
        return 1
    plan = build_cleanup_plan()
    deleted = 0
    if args.apply:
        for row in plan["delete_candidates"]:
            path = Path(row["path"])
            try:
                path.unlink(missing_ok=True)
                deleted += 1
            except OSError:
                continue
        plan["status"] = "APPLIED"
    plan["deleted_count"] = deleted
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
