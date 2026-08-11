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
DECISION_PLATFORMS = {"x", "threads", "tiktok"}
APPROVABLE_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
DECISION_REQUIRED_FLAGS = (
    "allow_download",
    "allow_cloudinary_storage",
    "allow_original_repost",
    "allow_transcription",
    "allow_analysis",
    "allow_cut",
    "allow_clip_repost",
    "allow_new_caption",
    "allow_edit",
)


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


def _handle(value: Any) -> str:
    text = str(value or "").strip().lstrip("@").lower()
    return f"@{text}" if text else ""


def load_owner_decision(path: Path) -> dict[str, Any]:
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("evidence_type") != "owner_attestation":
        raise ValueError("decision_evidence_type_must_be_owner_attestation")
    if not str(decision.get("evidence_reference") or "").strip():
        raise ValueError("decision_evidence_reference_required")
    if not str(decision.get("approved_by") or "").strip():
        raise ValueError("decision_approved_by_required")
    if set(decision.get("required_flags") or []) != set(DECISION_REQUIRED_FLAGS):
        raise ValueError("decision_required_flags_mismatch")
    return decision


def decision_sources(
    decision: dict[str, Any], source_ids: set[str] | None = None
) -> list[dict[str, Any]]:
    registry = json.loads(
        (ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8")
    ).get("sources", [])
    by_id = {str(row.get("source_id") or ""): row for row in registry}
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_identities: set[tuple[str, str, str]] = set()
    for item in decision.get("sources") or []:
        source_id = str(item.get("source_id") or "").strip()
        if source_ids is not None and source_id not in source_ids:
            continue
        if not source_id or source_id in seen_ids:
            raise ValueError(f"decision_source_id_duplicate_or_missing:{source_id}")
        source = by_id.get(source_id)
        if source is None:
            raise ValueError(f"decision_source_not_registered:{source_id}")
        platform = str(source.get("source_platform") or source.get("platform") or "").lower()
        registry_handle = _handle(source.get("source_handle") or source.get("author_handle"))
        decision_handle = _handle(item.get("source_handle"))
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        account_id = str(item.get("account_id") or "")
        if platform not in DECISION_PLATFORMS:
            raise ValueError(f"decision_platform_not_allowed:{source_id}:{platform}")
        if platform != str(item.get("platform") or "").lower():
            raise ValueError(f"decision_platform_mismatch:{source_id}")
        if not registry_handle or registry_handle != decision_handle:
            raise ValueError(f"decision_handle_mismatch:{source_id}")
        if account_id not in {str(value) for value in targets if value}:
            raise ValueError(f"decision_account_mismatch:{source_id}")
        identity = (platform, decision_handle, account_id)
        if identity in seen_identities:
            raise ValueError(f"decision_identity_duplicate:{platform}:{decision_handle}:{account_id}")
        selected.append({**source, **item, "source_handle": decision_handle})
        seen_ids.add(source_id)
        seen_identities.add(identity)
    if source_ids is not None and seen_ids != source_ids:
        missing = sorted(source_ids - seen_ids)
        raise ValueError(f"requested_source_not_in_decision:{','.join(missing)}")
    return selected


def permission_row(
    source: dict[str, Any],
    now: str,
    decision: dict[str, Any] | None = None,
) -> dict[str, str]:
    source_id = str(source["source_id"])
    platform = str(source.get("source_platform") or source.get("platform") or "").lower()
    # A Threads profile grant permits direct reuse of its original post media,
    # but never turns a profile into a clip factory.  Video-source grants retain
    # the explicit clip fields.  Existing revoked rows are still never touched.
    is_explicit_decision = decision is not None
    is_clip_source = is_explicit_decision or platform in {"youtube", "tiktok"}
    evidence_reference = (
        str(decision.get("evidence_reference") or "")
        if decision
        else "global_owner_attestation_v1"
    )
    approved_by = (
        str(decision.get("approved_by") or "") if decision else "Chadult株式会社"
    )
    allowed_platforms = ",".join(decision.get("allowed_platforms") or ["threads"]) if decision else "threads"
    account_id = str(
        source.get("account_id")
        or (source.get("target_account_ids") or [source.get("target_account_id")])[0]
        or ""
    )
    return {
        "permission_id": f"owner_attestation_{source_id}", "source_id": source_id,
        "source_handle": _handle(source.get("source_handle") or source.get("author_handle")),
        "source_url": str(source.get("canonical_url") or source.get("source_url") or ""),
        "account_id": account_id,
        "allowed_accounts": account_id,
        "allowed_platforms": allowed_platforms,
        "usage_mode": "direct_and_clip" if is_clip_source else "direct_media_reuse",
        "rights_status": "approved_creator_clip", "permission_status": "approved",
        "allow_download": "true", "allow_cloudinary_storage": "true", "allow_original_repost": "true",
        "allow_transcription": str(is_clip_source).lower(), "allow_analysis": "true", "allow_cut": str(is_clip_source).lower(),
        "allow_clip_repost": str(is_clip_source).lower(), "allow_new_caption": "true", "allow_edit": str(is_clip_source).lower(),
        "attribution_required": "false", "attribution_text": "",
        "evidence_type": "owner_attestation", "evidence_reference": evidence_reference,
        "approved_by": approved_by, "approved_at": now, "expires_at": "", "revoked": "false",
        "revoked_at": "", "notes": "Owner-attested for direct original reuse" + (" and generated clips." if is_clip_source else "."), "updated_at": now,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="seed global owner-attested media permissions")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-owner-attestation", action="store_true")
    parser.add_argument("--source-id", action="append", default=[], help="Explicit approved source ID; repeat for each source")
    parser.add_argument("--decision-file", help="Owner decision JSON with exact source/account/handle scope")
    args = parser.parse_args()
    if args.apply and not args.confirm_owner_attestation:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-owner-attestation"}))
        return 1
    if args.apply and not args.source_id:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires at least one explicit --source-id"}))
        return 1
    now = datetime.now(timezone.utc).isoformat()
    requested = {str(value).strip() for value in args.source_id if str(value).strip()} or None
    try:
        decision = load_owner_decision(Path(args.decision_file)) if args.decision_file else None
        sources = decision_sources(decision, requested) if decision else eligible_sources(requested)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    rows = [permission_row(source, now, decision) for source in sources]
    result: dict[str, Any] = {
        "status": "PLAN_ONLY",
        "eligible_source_count": len(rows),
        "requested_source_count": len(requested or []),
        "selected_source_ids": [row["source_id"] for row in rows],
        "selected_source_handles": [row["source_handle"] for row in rows],
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
    verified_rows = client._call_with_rate_limit_retry(
        "get_all_records:media_permissions:owner_seed_verify",
        lambda: ws.get_all_records(),
    )
    latest = {
        str(row.get("source_id", "")): dict(row)
        for row in verified_rows
        if row.get("source_id")
    }
    invalid_rows: list[dict[str, Any]] = []
    expected_by_id = {row["source_id"]: row for row in rows}
    for source_id, expected in expected_by_id.items():
        actual = latest.get(source_id, {})
        exact_fields = (
            "source_id",
            "source_handle",
            "account_id",
            "rights_status",
            "permission_status",
            "evidence_type",
            "evidence_reference",
            "approved_by",
            "approved_at",
        )
        invalid_fields = [
            field
            for field in exact_fields
            if str(actual.get(field, "")) != str(expected.get(field, ""))
        ]
        invalid_fields.extend(
            field for field in DECISION_REQUIRED_FLAGS if not truthy(actual.get(field))
        )
        if invalid_fields:
            invalid_rows.append({"source_id": source_id, "invalid_fields": invalid_fields})
    status = "APPLIED" if not invalid_rows else "PARTIAL_READ_AFTER_WRITE_FAILED"
    print(json.dumps({
        **result,
        "status": status,
        "written": writes,
        "updated": updates,
        "revoked_skipped": revoked_skips,
        "read_after_write": "PASS" if not invalid_rows else "FAIL",
        "invalid_rows": invalid_rows,
        "non_media_platforms_excluded": True,
    }, ensure_ascii=False, indent=2))
    return 0 if not invalid_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
