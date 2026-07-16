#!/usr/bin/env python3
"""Publish one explicitly permitted source-post video, or fill the slot safely.

This is deliberately separate from clip production.  A direct asset is always
joined to its originating ``source_post_id``; no runner can combine a caption
from one source post with media from another.  Source records without the
direct-media permission scope are plans only, even when clip permission exists.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from content_schedule import slot_by_id  # noqa: E402
from content_slot_runs import build_slot_run, existing_slot_status, upsert_slot_run  # noqa: E402
from media_post_validator import validate_media_post  # noqa: E402
from media_source_policy import DIRECT_SCOPE, decision  # noqa: E402
from process_threads_queue import append_row, process_one  # noqa: E402
from public_post_quality import final_public_post_validator, generate_grounded_reader_facing_post, public_preview  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402

POSTED_SLOT_STATUSES = {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED"}


def _true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return [dict(row) for row in client._ws(logical).get_all_records()]


def _source_map(client: SheetsClient) -> dict[str, dict[str, Any]]:
    rows = _records(client, "source_accounts")
    rows.extend(_records(client, "reference_sources"))
    return {str(row.get("source_id", "")): row for row in rows if row.get("source_id")}


def _permission_map(client: SheetsClient) -> dict[str, dict[str, Any]]:
    """Read user-entered rights; revoked/expired rows are never usable."""
    rows = _records(client, "media_permissions")
    result: dict[str, dict[str, Any]] = {}
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        source_id = str(row.get("source_id", ""))
        if not source_id or _true(row.get("revoked")):
            continue
        if str(row.get("expires_at", "")) and str(row["expires_at"]) < now:
            continue
        result[source_id] = row
    return result


def select_direct_candidate(client: SheetsClient, account_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Select one unused uploaded video with an explicit source-post linkage."""
    posts = {str(row.get("source_post_id", "")): row for row in _records(client, "source_posts")}
    sources = _source_map(client)
    permissions = _permission_map(client)
    posted = _records(client, "posted_results")
    assets_by_post = {
        str(row.get("reference_post_id", "")): row
        for row in _records(client, "media_assets")
    }
    used_assets = {str(row.get("media_asset_id", "")) for row in posted}
    reasons: list[str] = []
    selected: tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
    for media in _records(client, "source_post_media"):
        post_id = str(media.get("source_post_id", ""))
        post = posts.get(post_id)
        if not post:
            reasons.append("source_post_link_missing")
            continue
        if str(post.get("target_account_id", "")) != account_id:
            continue
        source = sources.get(str(post.get("source_id", "")), {})
        permission = permissions.get(str(post.get("source_id", "")), {})
        policy_fields = {key: post.get(key) or source.get(key, "") for key in ("rights_status", "permission_status", "permission_scope")}
        # The ledger has precedence and must explicitly allow every action.
        if permission:
            direct_allowed = all(_true(permission.get(key)) for key in ("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption"))
            source = {**source, "media_usage_mode": permission.get("usage_mode", "blocked")}
            policy_fields["permission_status"] = "approved" if direct_allowed else "denied"
            policy_fields["permission_scope"] = list(DIRECT_SCOPE) if direct_allowed else []
        policy = decision({**source, **policy_fields}, "direct_media")
        if not policy["allowed"]:
            reasons.append(f"{post_id}:{policy['reason']}")
            continue
        matching_asset = assets_by_post.get(post_id, {})
        media = {**matching_asset, **media} if matching_asset else media
        asset_id = str(media.get("media_asset_id") or media.get("media_id") or media.get("source_post_media_id") or "")
        if asset_id in used_assets or str(media.get("reuse_status", "")).upper() == "POSTED":
            reasons.append(f"{post_id}:already_posted")
            continue
        if str(media.get("cloudinary_status", "")).upper() != "UPLOADED" or not str(media.get("storage_url", "")):
            reasons.append(f"{post_id}:media_not_uploaded")
            continue
        media_type = str(media.get("media_type", "")).lower()
        if media_type not in {"video", "image"}:
            reasons.append(f"{post_id}:unsupported_media_type")
            continue
        selected = (post, media, source)
        break
    return (*selected, reasons) if selected else (None, None, None, reasons)


def build_plan(account_id: str, slot_id: str, client: SheetsClient | None, *, apply: bool) -> dict[str, Any]:
    slot = slot_by_id(account_id, slot_id)
    if not slot or slot.get("post_type") != "direct_reference_media":
        return {"status": "BLOCKED", "blocked_reasons": ["slot_id must be a direct_reference_media slot"]}
    if not client:
        return {"status": "PLAN_ONLY", "account_id": account_id, "slot_id": slot_id, "would_post": False, "blocked_reasons": []}
    post, media, _source, reasons = select_direct_candidate(client, account_id)
    if not post or not media:
        return {"status": "NO_POST", "account_id": account_id, "slot_id": slot_id, "would_post": False, "blocked_reasons": reasons[:30]}
    # Never expose original_post_text publicly. The account-specific generator
    # is intentionally based on a fresh reader-facing angle.
    text = str(generate_grounded_reader_facing_post(account_id, private_signal=str(post.get("original_post_text", "")), index=(sum(map(ord, str(post["source_post_id"]))) % 20) + 1)["public_post_text"])
    validation = final_public_post_validator(text, account_id)
    asset_id = str(media.get("media_asset_id") or media.get("source_post_media_id") or "")
    validator = validate_media_post({
        "rights_status": post.get("rights_status", ""), "permission_status": post.get("permission_status", ""),
        "media_url": media.get("storage_url", ""), "media_asset_id": asset_id, "platform": "threads",
        "account_id": account_id, "media_type": str(media.get("media_type", "video")), "duration_seconds": media.get("duration_seconds", 0),
        "aspect_ratio": str(media.get("aspect_ratio", "9:16")), "public_post_text": text,
    })
    return {
        "status": "WILL_APPLY" if apply and validation["status"] == "PASS" and validator["status"] == "PASS" else "PLAN_ONLY" if validation["status"] == "PASS" and validator["status"] == "PASS" else "BLOCKED",
        "account_id": account_id, "slot_id": slot_id, "source_post": post, "source_post_media": media,
        "source_post_id": post["source_post_id"], "media_asset_id": asset_id, "public_post_text": text,
        "public_post_preview": public_preview(text), "final_public_post_validator": validation["status"],
        "media_validator": validator["status"], "would_post": bool(apply and validator["status"] == "PASS"),
        "blocked_reasons": validation.get("blocked_reasons", []) + validator.get("blocked_reasons", []),
    }


def execute(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    if existing_slot_status(client, plan["account_id"], plan["slot_id"]) in POSTED_SLOT_STATUSES:
        return {**plan, "status": "SKIPPED", "reason": "slot_already_posted", "would_post": False}
    post, media = plan["source_post"], plan["source_post_media"]
    queue_id = f"direct_media_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{plan['account_id']}_{post['source_post_id']}"
    queue = {
        "queue_id": queue_id, "account_id": plan["account_id"], "target_account_id": plan["account_id"], "platform": "threads",
        "priority": "1", "status": "READY", "auto_publish": "true", "generation_mode": "direct_reference_media",
        "source_post_id": post["source_post_id"], "media_asset_id": plan["media_asset_id"], "media_url": media["storage_url"],
        "media_status": "UPLOADED", "media_required": "true", "media_type": media.get("media_type", "video"), "duration_seconds": media.get("duration_seconds", ""),
        "aspect_ratio": media.get("aspect_ratio", "9:16"), "rights_status": post.get("rights_status", ""), "permission_status": post.get("permission_status", ""),
        "public_post_text": plan["public_post_text"], "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if queue_id not in {str(row.get("queue_id", "")) for row in _records(client, "queue")}:
        append_row(client, "queue", queue)
    result = process_one(client, queue, dry_run=False, confirm_real_post=True)
    posted = str(result.get("status", "")) == "POSTED"
    slot = build_slot_run(plan["account_id"], plan["slot_id"], status="POSTED_PRIMARY" if posted else "FAILED", actual_post_type="direct_reference_media", fallback_level=0, source_post_id=post["source_post_id"], media_asset_id=plan["media_asset_id"], queue_id=queue_id, result_id=result.get("result_id", ""), post_url=result.get("post_url", ""), actual_posted_at=datetime.now(timezone.utc).isoformat() if posted else "", no_post_reason="" if posted else str(result.get("reason", result.get("status", "failed"))))
    upsert_slot_run(client, slot)
    return {**plan, "status": result.get("status", "FAILED"), "queue_id": queue_id, "post_result": result, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="post an explicitly permitted direct-reference media slot")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-direct-media", action="store_true")
    parser.add_argument("--fallback-to-text", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    client = None
    if args.use_sheets:
        cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    if args.apply and (not args.confirm_direct_media or not _true(os.environ.get("PUBLISH_ENABLED")) or not _true(os.environ.get("ALLOW_REAL_THREADS_POST")) or not _true(os.environ.get("ALLOW_MEDIA_POSTS")) or not _true(os.environ.get("ALLOW_REAL_THREADS_VIDEO_POST"))):
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["apply requires confirmation and all Threads media gates"]}, ensure_ascii=False)); return 1
    plan = build_plan(args.account_id, args.slot_id, client, apply=args.apply)
    if args.apply and client and plan.get("status") == "WILL_APPLY":
        plan = execute(plan, client)
    if args.apply and client and plan.get("status") in {"NO_POST", "FAILED", "BLOCKED_MEDIA_VALIDATOR", "SAFETY_STOP_MEDIA_GATE", "SAFETY_STOP_MEDIA_VALIDATOR"} and args.fallback_to_text:
        from run_slot_text_fallback import build_plan as fallback_plan, execute as fallback_execute
        fallback = fallback_execute(fallback_plan(args.account_id, args.slot_id, f"direct_reference_media_primary_{str(plan.get('status')).lower()}", apply=True), client)
        plan = {**plan, "status": fallback.get("status", "FAILED"), "fallback": fallback}
    safe = {key: value for key, value in plan.items() if key not in {"source_post", "source_post_media", "public_post_text"}}
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    return 1 if str(plan.get("status", "")).startswith(("FAILED", "BLOCKED")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
