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


def truthy(value: Any) -> bool:
    return value is True or str(value or "").lower() in {"1", "true", "yes"}


def eligible_sources() -> list[dict[str, Any]]:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8")).get("sources", [])
    result = []
    for source in sources:
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        platform = str(source.get("source_platform") or source.get("platform") or "").lower()
        if not truthy(source.get("active")) or platform == "x" or "beauty_account" in targets:
            continue
        result.append(source)
    return result


def permission_row(source: dict[str, Any], now: str) -> dict[str, str]:
    source_id = str(source["source_id"])
    return {
        "permission_id": f"owner_attestation_{source_id}", "source_id": source_id,
        "source_url": str(source.get("canonical_url") or source.get("source_url") or ""),
        "account_id": str((source.get("target_account_ids") or [source.get("target_account_id")])[0] or ""),
        "usage_mode": "direct_and_clip",
        "allow_download": "true", "allow_cloudinary_storage": "true", "allow_original_repost": "true",
        "allow_transcription": "true", "allow_analysis": "true", "allow_cut": "true",
        "allow_clip_repost": "true", "allow_new_caption": "true", "allow_edit": "true",
        "attribution_required": "false", "attribution_text": "",
        "evidence_type": "owner_attestation", "evidence_reference": "global_owner_attestation_v1",
        "approved_by": "Chadult株式会社", "approved_at": now, "expires_at": "", "revoked": "false",
        "revoked_at": "", "notes": "Owner-attested for direct original reuse and generated clips.", "updated_at": now,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="seed global owner-attested media permissions")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-owner-attestation", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_owner_attestation:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-owner-attestation"}))
        return 1
    now = datetime.now(timezone.utc).isoformat()
    rows = [permission_row(source, now) for source in eligible_sources()]
    result: dict[str, Any] = {"status": "PLAN_ONLY", "eligible_source_count": len(rows), "would_write": len(rows), "revoked_preserved": True}
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    ws = client._ensure_tab("media_permissions", TAB_DEFINITIONS["media_permissions"])
    headers = ws.row_values(1)
    existing = {str(row.get("source_id", "")): row for row in ws.get_all_records()}
    writes = 0
    for row in rows:
        previous = existing.get(row["source_id"])
        if previous and truthy(previous.get("revoked")):
            continue
        if previous:
            continue
        ws.append_row([row.get(header, "") for header in headers], value_input_option="USER_ENTERED")
        writes += 1
    print(json.dumps({**result, "status": "APPLIED", "written": writes, "existing_or_revoked_skipped": len(rows) - writes}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
