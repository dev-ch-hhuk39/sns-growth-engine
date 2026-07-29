#!/usr/bin/env python3
"""Register owner-attested canary assets without downloading, uploading or posting.

The importer intentionally has no network-media operation.  It records only
explicitly declared owned assets, and emits a rollback receipt for every apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ACCOUNTS = {"night_scout", "liver_manager"}
PURPOSES = {"direct_image", "direct_video", "direct_carousel", "generated_clip"}


def _sha256(value: str | Path) -> str:
    path = Path(value)
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _validate_asset(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    item = {key: raw.get(key) for key in raw}
    errors: list[str] = []
    asset_id = _text(item.get("asset_id"))
    group = _text(item.get("source_group_id")) or asset_id
    account_id = _text(item.get("account_id"))
    purpose = _text(item.get("asset_purpose"))
    canary_types = {str(value) for value in item.get("canary_types", [])} or {purpose}
    local_path = _text(item.get("local_path"))
    https_url = _text(item.get("https_url"))
    if not asset_id: errors.append("asset_id is required")
    if account_id not in ACCOUNTS: errors.append("account_id must be night_scout or liver_manager")
    if purpose not in PURPOSES: errors.append("asset_purpose is invalid")
    if bool(local_path) == bool(https_url): errors.append("provide exactly one of local_path or https_url")
    if https_url and not https_url.startswith("https://"): errors.append("https_url must use HTTPS")
    if local_path and not Path(local_path).is_file(): errors.append("local_path does not exist")
    if https_url and not _text(item.get("content_sha256")): errors.append("HTTPS assets require content_sha256")
    if _text(item.get("rights_status")) != "owned": errors.append("rights_status must be owned")
    if not _text(item.get("owner_declaration")): errors.append("owner_declaration is required")
    if item.get("threads_post_allowed") is not True: errors.append("threads_post_allowed must be true")
    if item.get("cloudinary_storage_allowed") is not True: errors.append("cloudinary_storage_allowed must be true")
    if not canary_types <= PURPOSES: errors.append("canary_types contains an invalid type")
    operations = {str(v) for v in item.get("allowed_operations", [])}
    required_operations = set()
    for canary_type in canary_types:
        required_operations.add("clip" if canary_type == "generated_clip" else ("carousel" if canary_type == "direct_carousel" else "direct"))
    if not required_operations <= operations: errors.append("allowed_operations does not cover canary_types")
    if "generated_clip" in canary_types:
        try:
            if float(item.get("clip_end_seconds")) <= float(item.get("clip_start_seconds")):
                errors.append("generated_clip requires clip_end_seconds greater than clip_start_seconds")
        except (TypeError, ValueError):
            errors.append("generated_clip requires numeric clip_start_seconds and clip_end_seconds")
    if not (_text(item.get("public_post_text")) or _text(item.get("queue_id"))):
        errors.append("public_post_text or queue_id is required")
    if errors:
        return None, errors
    item.update({"asset_id": asset_id, "source_group_id": group, "account_id": account_id, "asset_purpose": purpose, "canary_types": sorted(canary_types), "local_path": local_path, "https_url": https_url, "allowed_operations": sorted(operations)})
    item["content_hash"] = _sha256(local_path) if local_path else _text(item.get("content_sha256")).lower()
    return item, []


def build_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != 1 or not isinstance(payload.get("assets"), list):
        return {"status": "BLOCKED", "errors": ["schema_version=1 and assets array are required"]}
    assets: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(payload["assets"]):
        item, item_errors = _validate_asset(raw if isinstance(raw, dict) else {})
        if item_errors:
            errors.extend([f"assets[{index}]: {message}" for message in item_errors])
        elif item:
            if item["asset_id"] in seen: errors.append(f"duplicate asset_id: {item['asset_id']}")
            seen.add(item["asset_id"]); assets.append(item)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for asset in assets: groups[(asset["account_id"], asset["source_group_id"])].append(asset)
    for (_, group), members in groups.items():
        carousel = any("direct_carousel" in member["canary_types"] for member in members)
        if carousel and len(members) < 2: errors.append(f"carousel group {group} requires at least two media items")
        if len({member["media_order"] for member in members}) != len(members): errors.append(f"group {group} has duplicate media_order")
    return {"status": "BLOCKED" if errors else "PLAN_ONLY", "assets": assets, "groups": groups, "errors": errors}


def _row(headers: list[str], values: dict[str, Any]) -> list[str]:
    return ["" if values.get(header) is None else str(values.get(header, "")) for header in headers]


def _records(client: Any, logical: str) -> tuple[Any, list[str], list[dict[str, Any]]]:
    from sheets_client import TAB_DEFINITIONS
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    ws = client._ws(logical)
    return ws, ws.row_values(1), ws.get_all_records()


def apply_plan(plan: dict[str, Any]) -> dict[str, Any]:
    from config_loader import get_config
    from sheets_client import SheetsClient
    from public_post_quality import final_public_post_validator
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    tabs = {name: _records(client, name) for name in ("source_posts", "source_post_media", "media_permissions", "media_assets", "source_videos", "video_clip_candidates", "queue")}
    existing = {name: {str(row.get(key, "")) for row in rows} for name, (_, _, rows), key in (
        ("source_posts", tabs["source_posts"], "source_post_id"), ("source_post_media", tabs["source_post_media"], "source_post_media_id"),
        ("media_permissions", tabs["media_permissions"], "permission_id"), ("media_assets", tabs["media_assets"], "media_id"),
        ("source_videos", tabs["source_videos"], "source_video_id"), ("video_clip_candidates", tabs["video_clip_candidates"], "clip_candidate_id"), ("queue", tabs["queue"], "queue_id"))}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # media_assets predates the content_hash column; source_post_media is the
    # canonical persisted hash ledger for imported source bundles.
    existing_hashes = {str(row.get("content_hash", "")) for row in tabs["source_post_media"][2] if str(row.get("content_hash", ""))}
    duplicate_assets: list[dict[str, str]] = []
    receipt: dict[str, Any] = {"created_at": now, "operation": "import_owned_canary_assets", "rollback": {"delete_row_ids": defaultdict(list)}}
    for (account, group), members in plan["groups"].items():
        source_id = f"owned_source_{group}"; source_post_id = f"owned_source_post_{group}"; permission_id = f"owned_permission_{group}"
        combined_hash = _sha256("|".join(sorted(member["content_hash"] for member in members)))
        if source_post_id not in existing["source_posts"]:
            rows["source_posts"].append({"source_post_id": source_post_id, "source_id": source_id, "source_account_id": "owner_attested", "target_account_id": account, "platform": "owned_local", "canonical_post_url": "", "external_post_id": "", "original_post_text": "", "discovered_at": now, "media_count": len(members), "media_type": "carousel" if len(members) > 1 else members[0]["asset_purpose"], "collection_backend": "owner_asset_import", "rights_status": "owned", "permission_status": "approved", "permission_scope": "owner_declared", "direct_media_reuse_allowed": True, "collection_status": "OWNED_IMPORTED", "processing_status": "PENDING_MEDIA_PREP", "content_hash": combined_hash, "created_at": now, "updated_at": now})
            receipt["rollback"]["delete_row_ids"]["source_posts"].append(source_post_id)
        if permission_id not in existing["media_permissions"]:
            declaration = members[0]["owner_declaration"]
            rows["media_permissions"].append({"permission_id": permission_id, "source_id": source_id, "source_url": "", "account_id": account, "usage_mode": "direct_media", "permission_status": "approved", "rights_status": "owned", "allow_download": False, "allow_cloudinary_storage": True, "allow_original_repost": True, "allow_transcription": False, "allow_analysis": True, "allow_cut": any("clip" in member["allowed_operations"] for member in members), "allow_clip_repost": any("clip" in member["allowed_operations"] for member in members), "allow_new_caption": True, "allow_edit": any("clip" in member["allowed_operations"] for member in members), "attribution_required": False, "allowed_platforms": "threads", "allowed_accounts": account, "evidence_type": "owner_declaration", "evidence_reference": declaration, "approved_by": "owner", "approved_at": now, "expires_at": "", "revoked": False, "notes": "Owner-attested canary asset; no inferred third-party rights.", "updated_at": now})
            receipt["rollback"]["delete_row_ids"]["media_permissions"].append(permission_id)
        for member in members:
            media_id = f"owned_asset_{member['asset_id']}"; source_media_id = f"owned_source_media_{member['asset_id']}"
            if media_id in existing["media_assets"]:
                duplicate_assets.append({"asset_id": member["asset_id"], "reason": "media_asset_id_exists"}); continue
            if member["content_hash"] in existing_hashes:
                duplicate_assets.append({"asset_id": member["asset_id"], "reason": "content_hash_exists"}); continue
            media_type = "video" if member["asset_purpose"] in {"direct_video", "generated_clip"} else "image"
            original = member["https_url"]
            rows["source_post_media"].append({"source_post_media_id": source_media_id, "source_post_id": source_post_id, "media_index": member["media_order"], "original_media_url": original, "canonical_post_url": "", "acquisition_method": "owner_asset_import", "resolver_backend": "owner_local_file" if member["local_path"] else "owner_https", "media_type": media_type, "content_hash": member["content_hash"], "download_status": "NOT_REQUESTED", "cloudinary_status": "PENDING", "rights_status": "owned", "permission_status": "approved", "reuse_status": "APPROVED", "media_asset_id": media_id, "created_at": now, "updated_at": now})
            rows["media_assets"].append({"media_id": media_id, "account_id": account, "reference_post_id": source_post_id, "source_platform": "owned_local", "source_post_url": "", "original_media_url": original, "local_path": member["local_path"], "media_type": media_type, "storage_provider": "", "storage_url": "", "rights_status": "owned", "permission_status": "approved", "reuse_status": "approved_owner_asset", "rights_policy": "owned", "reuse_policy": "approved_owner_asset", "media_policy": "manual_media_prepare", "allow_download": False, "allow_cut": False, "allow_upload": False, "upload_status": "PENDING", "notes": f"content_hash={member['content_hash']}", "downloaded_at": "", "uploaded_at": ""})
            existing_hashes.add(member["content_hash"])
            receipt["rollback"]["delete_row_ids"]["source_post_media"].append(source_media_id); receipt["rollback"]["delete_row_ids"]["media_assets"].append(media_id)
            if "generated_clip" in member["canary_types"]:
                video_id = f"owned_video_{member['asset_id']}"; clip_id = f"owned_clip_{member['asset_id']}"
                rows["source_videos"].append({"source_video_id": video_id, "source_id": source_id, "account_id": account, "platform": "owned_local", "source_url": "", "video_id": member["asset_id"], "canonical_video_url": "", "title": "Owner-attested canary video", "transcript_status": "NOT_REQUESTED", "analysis_status": "OWNER_DECLARED", "rights_status": "owned", "permission_status": "approved", "discovery_status": "OWNED_IMPORTED", "content_hash": member["content_hash"], "discovered_at": now, "last_seen_at": now})
                rows["video_clip_candidates"].append({"clip_candidate_id": clip_id, "source_video_id": video_id, "source_id": source_id, "account_id": account, "platform": "owned_local", "start_seconds": member["clip_start_seconds"], "end_seconds": member["clip_end_seconds"], "duration_seconds": float(member["clip_end_seconds"]) - float(member["clip_start_seconds"]), "rights_status": "owned", "permission_status": "approved", "cut_status": "NOT_REQUESTED", "upload_status": "PENDING", "post_status": "NOT_POSTED", "reviewer_status": "WAITING_REVIEW", "created_at": now})
                receipt["rollback"]["delete_row_ids"]["source_videos"].append(video_id); receipt["rollback"]["delete_row_ids"]["video_clip_candidates"].append(clip_id)
        first = members[0]; public_text = _text(first.get("public_post_text")); queue_id = _text(first.get("queue_id"))
        if public_text:
            validation = final_public_post_validator(public_text, account_id=account)
            if validation.get("status") != "PASS":
                raise ValueError(f"public_post_text failed validator for {group}: {validation.get('blocked_reasons')}")
            requested_types = sorted({kind for member in members for kind in member["canary_types"]})
            for purpose in requested_types:
                scoped_queue_id = queue_id or f"owned_canary_{account}_{group}_{purpose}"
                if len(requested_types) > 1 and queue_id:
                    scoped_queue_id = f"{queue_id}_{purpose}"
                if scoped_queue_id in existing["queue"]: continue
                queue_row = {"queue_id": scoped_queue_id, "account_id": account, "platform": "threads", "status": "WAITING_REVIEW", "public_post_text": public_text, "source_post_id": source_post_id, "media_asset_id": f"owned_asset_{first['asset_id']}", "media_required": True, "media_type": purpose, "canary_id": f"canary_{account}_{purpose}", "created_at": now, "updated_at": now}
                if purpose == "direct_carousel":
                    queue_row["media_asset_ids_json"] = json.dumps([f"owned_asset_{member['asset_id']}" for member in sorted(members, key=lambda item: int(item["media_order"]))])
                rows["queue"].append(queue_row)
                receipt["rollback"]["delete_row_ids"]["queue"].append(scoped_queue_id)
    for logical, entries in rows.items():
        if entries:
            ws, headers, _ = tabs[logical]; ws.append_rows([_row(headers, entry) for entry in entries], value_input_option="USER_ENTERED")
    verification = {}
    for logical, ids in receipt["rollback"]["delete_row_ids"].items():
        _, _, after = _records(client, logical)
        key = {"source_posts": "source_post_id", "source_post_media": "source_post_media_id", "media_permissions": "permission_id", "media_assets": "media_id", "source_videos": "source_video_id", "video_clip_candidates": "clip_candidate_id", "queue": "queue_id"}[logical]
        present = {str(row.get(key, "")) for row in after}
        verification[logical] = {"expected": ids, "missing": [item for item in ids if item not in present], "status": "PASS" if all(item in present for item in ids) else "FAILED"}
    receipt["rollback"]["delete_row_ids"] = dict(receipt["rollback"]["delete_row_ids"])
    return {"status": "APPLIED" if all(item["status"] == "PASS" for item in verification.values()) else "PARTIAL_FAILURE", "scope": sorted({asset["account_id"] for asset in plan["assets"]}), "inserted": {name: len(value) for name, value in rows.items()}, "duplicate_assets_skipped": duplicate_assets, "read_after_write": verification, "rollback_receipt": receipt, "would_download": False, "would_cut": False, "would_upload": False, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-import-owned-assets", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    plan = build_plan(json.loads(args.input_json.read_text(encoding="utf-8")))
    if args.apply:
        if not args.confirm_import_owned_assets or not args.use_sheets:
            plan = {"status": "BLOCKED", "errors": ["--apply requires --confirm-import-owned-assets --use-sheets"]}
        elif plan["status"] != "PLAN_ONLY":
            pass
        else:
            try: plan = apply_plan(plan)
            except Exception as exc: plan = {"status": "PARTIAL_FAILURE", "error": str(exc), "rollback_required": True}
    plan.setdefault("would_download", False); plan.setdefault("would_cut", False); plan.setdefault("would_upload", False); plan.setdefault("would_post", False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0 if plan["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
