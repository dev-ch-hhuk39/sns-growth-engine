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
from content_slot_runs import business_date, build_slot_run, existing_slot_status, upsert_slot_run  # noqa: E402
from media_post_validator import validate_media_post  # noqa: E402
from media_source_policy import DIRECT_SCOPE, decision  # noqa: E402
from process_threads_queue import append_row, process_one  # noqa: E402
from public_post_quality import final_public_post_validator, generate_grounded_reader_facing_post, public_preview  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402

POSTED_SLOT_STATUSES = {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED"}
MEDIA_CONFIG = ROOT / "config/media_growth_engine.json"
AUTONOMOUS_CONFIG = ROOT / "config/autonomous_mode.json"


def _true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    # A direct-media plan reads several related tabs more than once.  Keep an
    # invocation-scoped snapshot to avoid spending Sheets quota on duplicate
    # reads during a scheduled run.  Write paths explicitly invalidate their
    # affected table below.
    cache = getattr(client, "_direct_media_records_cache", None)
    if cache is None:
        cache = {}
        setattr(client, "_direct_media_records_cache", cache)
    if logical in cache:
        return [dict(row) for row in cache[logical]]
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    rows = client._call_with_rate_limit_retry(
        f"get_all_records:{logical}",
        lambda: client._ws(logical).get_all_records(),
    )
    cache[logical] = [dict(row) for row in rows]
    return [dict(row) for row in cache[logical]]


def _invalidate_records(client: SheetsClient, *logical_names: str) -> None:
    cache = getattr(client, "_direct_media_records_cache", {})
    for logical in logical_names:
        cache.pop(logical, None)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _today_posts(rows: list[dict[str, Any]], account_id: str) -> list[dict[str, Any]]:
    target = business_date()
    result: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("account_id", "")) != account_id or str(row.get("status", "")).upper() != "POSTED":
            continue
        posted = _parse_time(row.get("posted_at"))
        if posted and business_date(posted) == target:
            result.append(row)
    return result


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
    """Select one complete source post; never combine media across parents."""
    posts = {str(row.get("source_post_id", "")): row for row in _records(client, "source_posts")}
    sources = _source_map(client)
    permissions = _permission_map(client)
    posted = _records(client, "posted_results")
    assets_by_post: dict[str, list[dict[str, Any]]] = {}
    for asset in _records(client, "media_assets"):
        assets_by_post.setdefault(str(asset.get("reference_post_id", "")), []).append(asset)
    media_by_post: dict[str, list[dict[str, Any]]] = {}
    for row in _records(client, "source_post_media"):
        media_by_post.setdefault(str(row.get("source_post_id", "")), []).append(row)
    used_assets = {str(row.get("media_asset_id", "")) for row in posted}
    reasons: list[str] = []
    selected: tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
    for post_id, media_rows in sorted(media_by_post.items()):
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
        resolved: list[dict[str, Any]] = []
        incomplete = False
        for media in sorted(media_rows, key=lambda row: int(str(row.get("media_index", "0") or "0"))):
            asset = next((row for row in assets_by_post.get(post_id, []) if str(row.get("original_media_url", "")) == str(media.get("original_media_url", ""))), {})
            merged = {**media, **{key: value for key, value in asset.items() if str(value or "").strip()}}
            asset_id = str(merged.get("media_asset_id") or merged.get("media_id") or merged.get("source_post_media_id") or "")
            if asset_id in used_assets or str(merged.get("reuse_status", "")).upper() == "POSTED":
                incomplete = True
                reasons.append(f"{post_id}:already_posted")
                break
            if str(merged.get("cloudinary_status", "")).upper() != "UPLOADED" or not str(merged.get("storage_url", "")):
                incomplete = True
                reasons.append(f"{post_id}:carousel_media_not_uploaded")
                break
            media_type = str(merged.get("media_type", "")).lower()
            if media_type not in {"video", "image"}:
                incomplete = True
                reasons.append(f"{post_id}:unsupported_media_type")
                break
            if media_type == "video":
                try:
                    duration = float(merged.get("duration_seconds") or 0)
                except (TypeError, ValueError):
                    duration = 0
                # Direct-reference media is the approved original asset, not
                # a generated 9:16 clip.  The strict 8-45s/9:16 validator is
                # intentionally reserved for the clip-production workflow.
                if duration > 300:
                    incomplete = True
                    reasons.append(f"{post_id}:video_media_not_postable")
                    break
            resolved.append(merged)
        if incomplete or not resolved:
            continue
        # A mixed carousel can be supported only by an explicit official API
        # gate later in the publisher.  Keep its parent intact either way.
        primary = {**resolved[0], "carousel_media": resolved}
        selected = (post, primary, source)
        break
    return (*selected, reasons) if selected else (None, None, None, reasons)


def build_plan(
    account_id: str,
    slot_id: str,
    client: SheetsClient | None,
    *,
    apply: bool,
    manual_e2e_proof: bool = False,
) -> dict[str, Any]:
    if manual_e2e_proof and slot_id:
        return {"status": "BLOCKED", "blocked_reasons": ["manual_e2e_proof must not claim a scheduled slot"]}
    slot = {"post_type": "direct_reference_media", "theme": "reader-facing account guidance"} if manual_e2e_proof else slot_by_id(account_id, slot_id)
    if not slot or slot.get("post_type") != "direct_reference_media":
        return {"status": "BLOCKED", "blocked_reasons": ["slot_id must be a direct_reference_media slot"]}
    if _true(os.environ.get("FORCE_TEXT_ONLY_FALLBACK")):
        return {
            "status": "NO_POST",
            "account_id": account_id,
            "slot_id": slot_id,
            "would_post": False,
            "blocked_reasons": ["resource_budget_text_only"],
        }
    if not client:
        return {"status": "PLAN_ONLY", "account_id": account_id, "slot_id": slot_id, "manual_e2e_proof": manual_e2e_proof, "would_post": False, "blocked_reasons": []}
    posted_rows = _records(client, "posted_results")
    today_posts = _today_posts(posted_rows, account_id)
    daily_cap = int(_load(AUTONOMOUS_CONFIG).get("daily_post_cap_per_account", 5))
    direct_cap = int(_load(MEDIA_CONFIG).get("direct_media_daily_post_cap", 1))
    direct_today = [row for row in today_posts if str(row.get("generation_mode", "")) == "direct_reference_media"]
    if len(today_posts) >= daily_cap:
        return {"status": "NO_POST", "account_id": account_id, "slot_id": slot_id, "manual_e2e_proof": manual_e2e_proof, "would_post": False, "today_post_count": len(today_posts), "blocked_reasons": ["daily_post_cap_reached"]}
    if len(direct_today) >= direct_cap:
        return {"status": "NO_POST", "account_id": account_id, "slot_id": slot_id, "manual_e2e_proof": manual_e2e_proof, "would_post": False, "today_direct_media_post_count": len(direct_today), "blocked_reasons": ["direct_media_daily_post_cap_reached"]}
    post, media, _source, reasons = select_direct_candidate(client, account_id)
    if not post or not media:
        return {"status": "NO_POST", "account_id": account_id, "slot_id": slot_id, "would_post": False, "blocked_reasons": reasons[:30]}
    # Never expose original_post_text publicly. The account-specific generator
    # is intentionally based on a fresh reader-facing angle.
    recent_posts = [
        str(row.get("posted_text", ""))
        for row in posted_rows
        if str(row.get("account_id", "")) == account_id
    ][-30:]
    grounded = generate_grounded_reader_facing_post(
        account_id,
        private_signal=str(post.get("original_post_text", "")),
        media_metadata={
            "media_type": media.get("media_type", ""),
            "duration_seconds": media.get("duration_seconds", ""),
            "aspect_ratio": media.get("aspect_ratio", ""),
        },
        slot_theme=str(slot.get("theme", "")),
        recent_posts=recent_posts,
        index=(sum(map(ord, str(post["source_post_id"]))) % 20) + 1,
    )
    text = str(grounded["public_post_text"])
    validation = final_public_post_validator(text, account_id)
    carousel_media = list(media.get("carousel_media") or [media])
    carousel_urls = [str(item.get("storage_url", "")) for item in carousel_media]
    carousel_asset_ids = [str(item.get("media_asset_id") or item.get("media_id") or item.get("source_post_media_id") or "") for item in carousel_media]
    carousel_types = [str(item.get("media_type", "")).lower() for item in carousel_media]
    asset_id = str(media.get("media_asset_id") or media.get("source_post_media_id") or "")
    validator = validate_media_post({
        "rights_status": post.get("rights_status", ""), "permission_status": post.get("permission_status", ""),
        "media_url": media.get("storage_url", ""), "media_asset_id": asset_id, "platform": "threads",
        "account_id": account_id, "media_type": str(media.get("media_type", "video")), "duration_seconds": media.get("duration_seconds", 0),
        "aspect_ratio": str(media.get("aspect_ratio", "")), "public_post_text": text,
        "media_origin": "direct_reference",
    })
    return {
        "status": "WILL_APPLY" if apply and validation["status"] == "PASS" and validator["status"] == "PASS" else "PLAN_ONLY" if validation["status"] == "PASS" and validator["status"] == "PASS" else "BLOCKED",
        "account_id": account_id, "slot_id": slot_id, "manual_e2e_proof": manual_e2e_proof, "source_post": post, "source_post_media": media,
        "source_post_id": post["source_post_id"], "media_asset_id": asset_id, "public_post_text": text,
        "media_asset_ids": carousel_asset_ids, "media_urls": carousel_urls, "media_types": carousel_types,
        "today_post_count": len(today_posts), "today_direct_media_post_count": len(direct_today),
        "daily_post_cap": daily_cap, "direct_media_daily_post_cap": direct_cap,
        "public_post_preview": public_preview(text), "final_public_post_validator": validation["status"],
        "grounding_summary": grounded.get("grounding_summary", {}),
        "transformation_summary": grounded.get("transformation_summary", ""),
        "similarity_score": grounded.get("similarity_score", 1.0),
        "recent_post_similarity_score": grounded.get("recent_post_similarity_score", 1.0),
        "media_validator": validator["status"], "would_post": bool(apply and validator["status"] == "PASS"),
        "blocked_reasons": validation.get("blocked_reasons", []) + validator.get("blocked_reasons", []),
    }


def execute(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    if plan.get("slot_id") and existing_slot_status(client, plan["account_id"], plan["slot_id"]) in POSTED_SLOT_STATUSES:
        return {**plan, "status": "SKIPPED", "reason": "slot_already_posted", "would_post": False}
    post, media = plan["source_post"], plan["source_post_media"]
    queue_id = f"direct_media_{business_date().replace('-', '')}_{plan['account_id']}_{post['source_post_id']}_{plan['media_asset_id']}"
    queue = {
        "queue_id": queue_id, "account_id": plan["account_id"], "target_account_id": plan["account_id"], "platform": "threads",
        "priority": "1", "status": "READY", "auto_publish": "true", "generation_mode": "direct_reference_media",
        "source_post_id": post["source_post_id"], "source_id": post.get("source_id", ""), "source_url": post.get("post_url", ""),
        "media_asset_id": plan["media_asset_id"], "media_url": media["storage_url"],
        "media_asset_ids_json": json.dumps(plan.get("media_asset_ids", [])),
        "media_urls_json": json.dumps(plan.get("media_urls", [])),
        "media_types_json": json.dumps(plan.get("media_types", [])),
        "media_status": "UPLOADED", "media_required": "true", "media_type": media.get("media_type", "video"), "duration_seconds": media.get("duration_seconds", ""),
        "aspect_ratio": media.get("aspect_ratio", ""), "rights_status": post.get("rights_status", ""), "permission_status": post.get("permission_status", ""),
        "public_post_text": plan["public_post_text"], "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if queue_id not in {str(row.get("queue_id", "")) for row in _records(client, "queue")}:
        append_row(client, "queue", queue)
        _invalidate_records(client, "queue")
    result = process_one(client, queue, dry_run=False, confirm_real_post=True)
    posted = str(result.get("status", "")) == "POSTED"
    if plan.get("slot_id"):
        slot = build_slot_run(plan["account_id"], plan["slot_id"], status="POSTED_PRIMARY" if posted else "FAILED", actual_post_type="direct_reference_media", fallback_level=0, source_post_id=post["source_post_id"], media_asset_id=plan["media_asset_id"], queue_id=queue_id, result_id=result.get("result_id", ""), post_url=result.get("post_url", ""), actual_posted_at=datetime.now(timezone.utc).isoformat() if posted else "", no_post_reason="" if posted else str(result.get("reason", result.get("status", "failed"))))
        slot_result = upsert_slot_run(client, slot)
    else:
        slot_result = {"status": "SKIPPED", "reason": "manual_e2e_proof_does_not_claim_scheduled_slot"}
    return {**plan, "status": result.get("status", "FAILED"), "queue_id": queue_id, "post_result": result, "content_slot_run": slot_result, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="post an explicitly permitted direct-reference media slot")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--slot-id", default="")
    parser.add_argument("--manual-e2e-proof", action="store_true", help="workflow_dispatch-only proof; never claims a scheduled slot")
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
    if not args.slot_id and not args.manual_e2e_proof:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["--slot-id or --manual-e2e-proof is required"]}, ensure_ascii=False)); return 1
    plan = build_plan(args.account_id, args.slot_id, client, apply=args.apply, manual_e2e_proof=args.manual_e2e_proof)
    if args.apply and client and plan.get("status") == "WILL_APPLY":
        plan = execute(plan, client)
    if args.apply and client and plan.get("status") in {"NO_POST", "FAILED", "BLOCKED", "BLOCKED_MEDIA_VALIDATOR", "SAFETY_STOP_MEDIA_GATE", "SAFETY_STOP_MEDIA_VALIDATOR"} and args.fallback_to_text:
        if args.manual_e2e_proof:
            print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["manual_e2e_proof cannot use scheduled text fallback"]}, ensure_ascii=False)); return 1
        from run_slot_text_fallback import build_plan as fallback_plan, execute as fallback_execute
        fallback = fallback_execute(fallback_plan(args.account_id, args.slot_id, f"direct_reference_media_primary_{str(plan.get('status')).lower()}", apply=True), client)
        plan = {**plan, "status": fallback.get("status", "FAILED"), "fallback": fallback}
    def safe_output(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: safe_output(item)
                for key, item in value.items()
                if key not in {"source_post", "source_post_media", "public_post_text", "internal_analysis", "safety_notes"}
            }
        if isinstance(value, list):
            return [safe_output(item) for item in value]
        return value
    safe = safe_output(plan)
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    return 1 if str(plan.get("status", "")).startswith(("FAILED", "BLOCKED")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
