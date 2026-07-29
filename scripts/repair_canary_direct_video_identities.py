#!/usr/bin/env python3
"""Repair only the two approved direct-video parents needed by the 12 canaries."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from apply_source_identity_repairs import apply_to_sheets
from source_identity_repair_contract import _parent_snapshot_hash, row_fingerprint
from source_identity_repair_executor import apply_plan_in_memory, production_apply_allowed


TARGETS = {
    "sp_src_ns_yt_cand_001_8Xmkojfw90Q": {
        "source_id": "src_ns_yt_cand_001",
        "external_post_id": "8Xmkojfw90Q",
        "canonical_post_url": "https://www.youtube.com/watch?v=8Xmkojfw90Q",
    },
    "sp_src_lm_tt_user_001_7662652624092597522": {
        "source_id": "src_lm_tt_user_001",
        "external_post_id": "7662652624092597522",
        "canonical_post_url": "https://www.tiktok.com/@user5597696107300/video/7662652624092597522",
    },
}


def build_plan(datasets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    repairs: list[dict[str, Any]] = []
    for source_post_id, expected in TARGETS.items():
        parents = [row for row in datasets.get("source_posts", []) if str(row.get("source_post_id", "")) == source_post_id]
        if len(parents) != 1:
            raise RuntimeError(f"PARENT_NOT_UNIQUELY_RESOLVABLE:{source_post_id}")
        parent = parents[0]
        if str(parent.get("source_id", "")) != expected["source_id"]:
            raise RuntimeError(f"SOURCE_ID_PRECONDITION_FAILED:{source_post_id}")
        if str(parent.get("external_post_id", "")) != expected["external_post_id"]:
            raise RuntimeError(f"EXTERNAL_POST_ID_PRECONDITION_FAILED:{source_post_id}")
        operations: list[dict[str, Any]] = [{
            "operation": "SET_PARENT_CANONICAL_URL",
            "to": expected["canonical_post_url"],
            "row_fingerprint": row_fingerprint(parent),
            "reason": "CANARY_DIRECT_VIDEO_PARENT_MUST_BE_INDIVIDUAL_POST",
        }]
        children = [row for row in datasets.get("source_post_media", []) if str(row.get("source_post_id", "")) == source_post_id]
        if not children:
            raise RuntimeError(f"CHILD_MEDIA_MISSING:{source_post_id}")
        for child in children:
            operations.append({
                "operation": "SET_CHILD_CANONICAL_URL_BY_FINGERPRINT",
                "source_post_media_id": str(child.get("source_post_media_id", "")),
                "to": expected["canonical_post_url"],
                "row_fingerprint": row_fingerprint(child),
                "reason": "CANARY_DIRECT_VIDEO_CHILD_ALIGNS_TO_INDIVIDUAL_PARENT",
            })
        repairs.append({
            "source_post_id": source_post_id,
            "account_id": str(parent.get("target_account_id") or parent.get("account_id") or ""),
            "operations": operations,
            "blocker_codes": [],
            "apply_eligible": True,
            "before_snapshot_hash": _parent_snapshot_hash(source_post_id, datasets),
            "resolution_kind": "CANARY_DIRECT_VIDEO_INDIVIDUAL_POST_REPAIR",
        })
    return {
        "schema_version": 1,
        "mode": "CANARY_DIRECT_VIDEO_IDENTITY_REPAIR",
        "repair_plan_id": "canary_direct_video_identity_v1",
        "implementation_head": "runtime",
        "origin_main": "runtime",
        "verification_scope": "CANARY_DIRECT_VIDEO_URL_ONLY",
        "parent_repairs": repairs,
        "affected_parent_ids": sorted(TARGETS),
        "apply_allowed": False,
    }


def _read(client: Any) -> dict[str, list[dict[str, Any]]]:
    return {name: [dict(row) for row in client._ws(name).get_all_records()] for name in ("source_posts", "source_post_media")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-canary-source-repair", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
    datasets = _read(client)
    try:
        plan = build_plan(datasets)
        if args.apply:
            if not production_apply_allowed(apply=True, confirm=args.confirm_canary_source_repair):
                result = {"status": "BLOCKED", "reason": "ALLOW_SHEETS_IDENTITY_REPAIR=true and --confirm-canary-source-repair are required"}
            else:
                result = apply_to_sheets(client, plan)
        else:
            result = apply_plan_in_memory(plan, datasets)
            result["mode"] = "DRY_RUN_NO_SHEETS_WRITE"
        result["repair_plan"] = plan
    except Exception as exc:
        result = {"status": "BLOCKED", "reason": str(exc), "mode": "NO_WRITE"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result.get("status"), "mode": result.get("mode", "APPLY" if args.apply else "DRY_RUN")}, ensure_ascii=False))
    return 0 if result.get("status") == "APPLIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
