#!/usr/bin/env python3
"""Seed the owner-attested permission ledger without reviving revoked grants.

The owner has supplied a global attestation for active non-X, non-beauty
sources.  This script is deliberately separate from discovery and never
downloads, uploads, or posts media.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config
from sheets_client import TAB_DEFINITIONS, SheetsClient

MEDIA_CAPABLE_PLATFORMS = {"threads", "youtube", "tiktok"}
APPROVABLE_RIGHTS = {"owned", "licensed", "approved_creator_clip"}


def truthy(value: Any) -> bool:
    return value is True or str(value or "").lower() in {"1", "true", "yes"}


def eligible_sources(source_ids: set[str] | None = None) -> list[dict[str, Any]]:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8")).get("sources", [])
    result = []
    for source in sources:
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        platform = str(source.get("source_platform") or source.get("platform") or "").lower()
        if source_ids is not None and str(source.get("source_id", "")) not in source_ids:
            continue
        if platform not in MEDIA_CAPABLE_PLATFORMS or "beauty_account" in targets:
            continue
        if str(source.get("rights_status", "")).lower() not in APPROVABLE_RIGHTS:
            continue
        if str(source.get("permission_status", "")).lower() != "approved":
            continue
        result.append(source)
    return result


def permission_row(source: dict[str, Any], now: str) -> dict[str, str]:
    source_id = str(source["source_id"])
    platform = str(source.get("source_platform") or source.get("platform") or "").lower()
    # A Threads profile grant permits direct reuse of its original post media,
    # but never turns a profile into a clip factory.  Video-source grants retain
    # the explicit clip fields.  Existing revoked rows are still never touched.
    is_clip_source = platform in {"youtube", "tiktok"}
    return {
        "permission_id": f"owner_attestation_{source_id}", "source_id": source_id,
        "source_url": str(source.get("canonical_url") or source.get("source_url") or ""),
        "account_id": str((source.get("target_account_ids") or [source.get("target_account_id")])[0] or ""),
        "usage_mode": "direct_and_clip" if is_clip_source else "direct_media_reuse",
        "rights_status": "approved_creator_clip", "permission_status": "approved",
        "allow_download": "true", "allow_cloudinary_storage": "true", "allow_original_repost": "true",
        "allow_transcription": str(is_clip_source).lower(), "allow_analysis": "true", "allow_cut": str(is_clip_source).lower(),
        "allow_clip_repost": str(is_clip_source).lower(), "allow_new_caption": "true", "allow_edit": str(is_clip_source).lower(),
        "attribution_required": "false", "attribution_text": "",
        "evidence_type": "owner_attestation", "evidence_reference": "global_owner_attestation_v1",
        "approved_by": "Chadult株式会社", "approved_at": now, "expires_at": "", "revoked": "false",
        "revoked_at": "", "notes": "Owner-attested for direct original reuse" + (" and generated clips." if is_clip_source else "."), "updated_at": now,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="seed global owner-attested media permissions")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-owner-attestation", action="store_true")
    parser.add_argument("--source-id", action="append", default=[], help="Explicit approved source ID; repeat for each source")
    args = parser.parse_args()
    if args.apply and not args.confirm_owner_attestation:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-owner-attestation"}))
        return 1
    if args.apply and not args.source_id:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires at least one explicit --source-id"}))
        return 1
    now = datetime.now(timezone.utc).isoformat()
    requested = {str(value).strip() for value in args.source_id if str(value).strip()} or None
    rows = [permission_row(source, now) for source in eligible_sources(requested)]
    result: dict[str, Any] = {
        "status": "PLAN_ONLY",
        "eligible_source_count": len(rows),
        "requested_source_count": len(requested or []),
        "selected_source_ids": [row["source_id"] for row in rows],
        "would_write": len(rows),
        "revoked_preserved": True,
        "approved_rights_only": True,
    }
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    ws = client._ensure_tab("media_permissions", TAB_DEFINITIONS["media_permissions"])
    headers = client._call_with_rate_limit_retry(
        "row_values:media_permissions:owner_seed",
        lambda: ws.row_values(1),
    )
    existing_rows = client._call_with_rate_limit_retry(
        "get_all_records:media_permissions:owner_seed",
        lambda: ws.get_all_records(),
    )
    existing = {
        str(row.get("source_id", "")): (row_number, dict(row))
        for row_number, row in enumerate(existing_rows, start=2)
    }
    writes = updates = revoked_skips = 0
    for row in rows:
        previous_entry = existing.get(row["source_id"])
        previous = previous_entry[1] if previous_entry else None
        if previous and truthy(previous.get("revoked")):
            revoked_skips += 1
            continue
        if previous_entry:
            row_number = previous_entry[0]
            client._call_with_rate_limit_retry(
                f"update:media_permissions:{row['source_id']}",
                lambda row_number=row_number, row=row: ws.update(
                    [[str(row.get(header, "")) for header in headers]],
                    f"A{row_number}",
                ),
            )
            updates += 1
            continue
        client._call_with_rate_limit_retry(
            f"append_row:media_permissions:{row['source_id']}",
            lambda row=row: ws.append_row(
                [row.get(header, "") for header in headers],
                value_input_option="USER_ENTERED",
            ),
        )
        writes += 1
    print(json.dumps({
        **result,
        "status": "APPLIED",
        "written": writes,
        "updated": updates,
        "revoked_skipped": revoked_skips,
        "non_media_platforms_excluded": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
