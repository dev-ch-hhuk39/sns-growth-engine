#!/usr/bin/env python3
"""Publish one explicitly permitted source-post video, or fill the slot safely.

This is deliberately separate from clip production.  A direct asset is always
joined to its originating ``source_post_id``; no runner can combine a caption
from one source post with media from another.  Source records without the
direct-media permission scope are plans only, even when clip permission exists.
"""
from __future__ import annotations

import argparse
import hashlib
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
from content_slot_runs import business_date, build_slot_run, claim_slot_run, existing_slot_status, upsert_slot_run  # noqa: E402
from media_post_validator import validate_media_post  # noqa: E402
from media_source_policy import DIRECT_SCOPE, decision  # noqa: E402
from process_threads_queue import append_row, process_one  # noqa: E402
from public_post_quality import final_public_post_validator, generate_grounded_reader_facing_post, public_preview  # noqa: E402
from generation.source_grounded_caption import (  # noqa: E402
    GitHubModelsGroundedProvider,
    SourceGroundedCaptionService,
    build_source_post_bundle,
)
from acquisition.reliability import (  # noqa: E402
    build_quarantine_record,
    is_quarantined,
    register_failure,
)
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
        if not str(row.get("evidence_type", "")).strip() or not str(row.get("evidence_reference", "")).strip():
            continue
        normalized = dict(row)
        normalized["rights_status"] = str(row.get("rights_status") or "approved_creator_clip")
        normalized["permission_status"] = "approved"
        result[source_id] = normalized
    return result


def select_direct_candidates(
    client: SheetsClient,
    account_id: str,
) -> tuple[list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]], list[str]]:
    """Return complete parent-preserving candidates in deterministic order."""
    posts = {str(row.get("source_post_id", "")): row for row in _records(client, "source_posts")}
    sources = _source_map(client)
    permissions = _permission_map(client)
    posted = _records(client, "posted_results")
    source_usage: dict[str, int] = {}
    for row in posted:
        if str(row.get("account_id", "")) != account_id or str(row.get("status", "")).upper() != "POSTED":
            continue
        source_id = str(row.get("source_id", ""))
        if source_id:
            source_usage[source_id] = source_usage.get(source_id, 0) + 1
    queued = _records(client, "queue")
    assets_by_post: dict[str, list[dict[str, Any]]] = {}
    for asset in _records(client, "media_assets"):
        assets_by_post.setdefault(str(asset.get("reference_post_id", "")), []).append(asset)
    media_by_post: dict[str, list[dict[str, Any]]] = {}
    for row in _records(client, "source_post_media"):
        media_by_post.setdefault(str(row.get("source_post_id", "")), []).append(row)
    understanding_by_media = {
        str(row.get("source_post_media_id", "")): row
        for row in _records(client, "source_media_understanding")
    }
    used_assets = {str(row.get("media_asset_id", "")) for row in posted}
    used_assets.update(
        str(row.get("media_asset_id", ""))
        for row in queued
        if str(row.get("status", "")).upper() in {"READY", "MEDIA_READY", "PROCESSING"}
    )
    reasons: list[str] = []
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for post_id, media_rows in sorted(media_by_post.items()):
        post = posts.get(post_id)
        if not post:
            reasons.append("source_post_link_missing")
            continue
        if str(post.get("target_account_id", "")) != account_id:
            continue
        if is_quarantined(post):
            reasons.append(f"{post_id}:source_post_quarantined")
            continue
        source = sources.get(str(post.get("source_id", "")), {})
        permission = permissions.get(str(post.get("source_id", "")), {})
        policy_fields = {key: post.get(key) or source.get(key, "") for key in ("rights_status", "permission_status", "permission_scope")}
        # The ledger has precedence and must explicitly allow every action.
        if permission:
            direct_allowed = all(_true(permission.get(key)) for key in ("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption"))
            source = {**source, "media_usage_mode": permission.get("usage_mode", "blocked")}
            policy_fields["rights_status"] = permission.get("rights_status", "approved_creator_clip")
            policy_fields["permission_status"] = "approved" if direct_allowed else "denied"
            policy_fields["permission_scope"] = list(DIRECT_SCOPE) if direct_allowed else []
        policy = decision({**source, **policy_fields}, "direct_media")
        if not policy["allowed"]:
            reasons.append(f"{post_id}:{policy['reason']}")
            continue
        resolved: list[dict[str, Any]] = []
        incomplete = False
        for media in sorted(media_rows, key=lambda row: int(str(row.get("media_index", "0") or "0"))):
            if is_quarantined(media):
                incomplete = True
                reasons.append(f"{post_id}:media_quarantined")
                break
            asset = next((row for row in assets_by_post.get(post_id, []) if str(row.get("original_media_url", "")) == str(media.get("original_media_url", ""))), {})
            merged = {**media, **{key: value for key, value in asset.items() if str(value or "").strip()}}
            understanding = understanding_by_media.get(str(media.get("source_post_media_id", "")), {})
            if str(understanding.get("status", "")).upper() != "PASS":
                incomplete = True
                reasons.append(f"{post_id}:media_content_understanding_missing")
                break
            merged["media_understanding"] = understanding
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
        candidates.append((post, primary, source))
    def candidate_key(candidate: tuple[dict[str, Any], dict[str, Any], dict[str, Any]]):
        post, _media, source = candidate
        source_id = str(post.get("source_id", ""))
        try:
            priority = float(source.get("priority") or 0)
        except (TypeError, ValueError):
            priority = 0.0
        published = _parse_time(post.get("published_at"))
        published_rank = -(published.timestamp()) if published else 0.0
        return source_usage.get(source_id, 0), -priority, published_rank, str(post.get("source_post_id", ""))
    candidates.sort(key=candidate_key)
    return candidates, reasons


def select_direct_candidate(client: SheetsClient, account_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Compatibility wrapper returning the first complete candidate."""
    candidates, reasons = select_direct_candidates(client, account_id)
    return (*candidates[0], reasons) if candidates else (None, None, None, reasons)


def _update_record(
    client: SheetsClient,
    logical: str,
    id_field: str,
    id_value: str,
    fields: dict[str, Any],
) -> bool:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    ws = client._ws(logical)
    headers = client._call_with_rate_limit_retry(
        f"row_values:{logical}:reliability", lambda: ws.row_values(1)
    )
    if id_field not in headers:
        return False
    cell = client._call_with_rate_limit_retry(
        f"find:{logical}:{id_value}:reliability",
        lambda: ws.find(id_value, in_column=headers.index(id_field) + 1),
    )
    if not cell:
        return False
    client._batch_update_fields(ws, headers, cell.row, fields, label=f"{logical}:{id_value}:reliability")
    _invalidate_records(client, logical)
    return True


def _record_candidate_failure(
    client: SheetsClient,
    *,
    post: dict[str, Any],
    media: dict[str, Any],
    account_id: str,
    reason: str,
) -> dict[str, Any]:
    entity_id = str(media.get("source_post_media_id") or media.get("media_asset_id") or post.get("source_post_id") or "")
    state = register_failure(media, reason)
    _update_record(
        client,
        "source_post_media",
        "source_post_media_id",
        str(media.get("source_post_media_id", "")),
        {key: state.get(key, "") for key in (
            "retry_count", "last_error", "failure_signature", "same_failure_count",
            "last_attempt_at", "quarantined_at", "quarantine_reason",
        )},
    )
    if is_quarantined(state):
        row = build_quarantine_record(
            state,
            entity_type="source_post_media",
            entity_id=entity_id,
            source_id=str(post.get("source_id", "")),
            account_id=account_id,
        )
        existing = {str(item.get("quarantine_id", "")) for item in _records(client, "quarantined_items")}
        if row["quarantine_id"] not in existing:
            append_row(client, "quarantined_items", row)
            _invalidate_records(client, "quarantined_items")
    return state


def _record_caption_attempt(
    client: SheetsClient,
    *,
    post: dict[str, Any],
    account_id: str,
    grounded: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc)
    suffix = str(int(now.timestamp() * 1_000_000))
    analysis = grounded.get("internal_analysis") if isinstance(grounded.get("internal_analysis"), dict) else {}
    alignment = grounded.get("semantic_alignment") if isinstance(grounded.get("semantic_alignment"), dict) else {}
    public_text = str(grounded.get("public_post_text", ""))
    append_row(client, "content_understanding_runs", {
        "understanding_id": f"cu_{post.get('source_post_id', '')}_{suffix}",
        "source_id": post.get("source_id", ""),
        "source_post_id": post.get("source_post_id", ""),
        "account_id": account_id,
        "platform": "threads",
        "main_claims_json": json.dumps(analysis.get("main_claims", []), ensure_ascii=False),
        "topic": analysis.get("topic") or analysis.get("core_topic", ""),
        "audience": analysis.get("audience") or analysis.get("intended_audience", ""),
        "core_topic": analysis.get("core_topic") or analysis.get("topic", ""),
        "main_claim": analysis.get("main_claim", ""),
        "hook": analysis.get("hook", ""),
        "supporting_points_json": json.dumps(analysis.get("supporting_points", []), ensure_ascii=False),
        "concrete_example": analysis.get("concrete_example", ""),
        "conclusion": analysis.get("conclusion", ""),
        "intended_audience": analysis.get("intended_audience") or analysis.get("audience", ""),
        "media_role": analysis.get("media_role", ""),
        "factual_constraints_json": json.dumps(analysis.get("factual_constraints", []), ensure_ascii=False),
        "prohibited_inferences_json": json.dumps(analysis.get("prohibited_inferences", []), ensure_ascii=False),
        "comment_signal_count": post.get("comment_count_collected", "0"),
        "media_item_count": len(post.get("media_items", []) or []),
        "provider_name": grounded.get("provider_name", ""),
        "provider_version": grounded.get("provider_version", ""),
        "status": grounded.get("status", "BLOCKED"),
        "content_hash": post.get("content_hash", ""),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    })
    append_row(client, "semantic_alignment_runs", {
        "alignment_id": f"sa_{post.get('source_post_id', '')}_{suffix}",
        "source_id": post.get("source_id", ""),
        "source_post_id": post.get("source_post_id", ""),
        "account_id": account_id,
        "platform": "threads",
        "caption_provider": grounded.get("provider_name", ""),
        "caption_provider_version": grounded.get("provider_version", ""),
        "status": alignment.get("status", "BLOCKED"),
        "final_alignment_score": alignment.get("final_alignment_score", ""),
        "main_claim_coverage": alignment.get("main_claim_coverage", ""),
        "unsupported_claim_count": alignment.get("unsupported_claim_count", ""),
        "source_copy_similarity": alignment.get("source_copy_similarity", ""),
        "recent_post_similarity": alignment.get("recent_post_similarity", ""),
        "claim_support_json": json.dumps(grounded.get("claim_support", []), ensure_ascii=False),
        "blocked_reasons": json.dumps(grounded.get("blocked_reasons", []), ensure_ascii=False),
        "source_content_hash": post.get("content_hash", ""),
        "public_post_hash": hashlib.sha256(public_text.encode("utf-8")).hexdigest() if public_text else "",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    })


def build_plan(
    account_id: str,
    slot_id: str,
    client: SheetsClient | None,
    *,
    apply: bool,
    manual_e2e_proof: bool = False,
    prepare_only: bool = False,
    caption_service: SourceGroundedCaptionService | None = None,
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
    if not prepare_only and len(today_posts) >= daily_cap:
        return {"status": "NO_POST", "account_id": account_id, "slot_id": slot_id, "manual_e2e_proof": manual_e2e_proof, "would_post": False, "today_post_count": len(today_posts), "blocked_reasons": ["daily_post_cap_reached"]}
    if not prepare_only and len(direct_today) >= direct_cap:
        return {"status": "NO_POST", "account_id": account_id, "slot_id": slot_id, "manual_e2e_proof": manual_e2e_proof, "would_post": False, "today_direct_media_post_count": len(direct_today), "blocked_reasons": ["direct_media_daily_post_cap_reached"]}
    candidates, reasons = select_direct_candidates(client, account_id)
    if not candidates:
        return {"status": "NO_POST", "account_id": account_id, "slot_id": slot_id, "would_post": False, "blocked_reasons": reasons[:30]}
    recent_posts = [
        str(row.get("posted_text", ""))
        for row in posted_rows
        if str(row.get("account_id", "")) == account_id
    ][-30:]
    caption_service = caption_service or SourceGroundedCaptionService(GitHubModelsGroundedProvider())
    attempted: list[dict[str, Any]] = []
    for post, media, _source in candidates:
        # Never expose original_post_text publicly. A source-specific provider
        # maps every public claim back to this exact source_post_id.
        carousel_media = list(media.get("carousel_media") or [media])
        bundle = build_source_post_bundle(post, carousel_media)
        media_evidence_parts: list[str] = []
        for item in carousel_media:
            understanding = item.get("media_understanding") if isinstance(item.get("media_understanding"), dict) else {}
            media_evidence_parts.extend(str(understanding.get(key, "")) for key in (
                "visual_summary", "visible_text", "ocr_text", "transcript_text",
            ))
        media_evidence = "\n".join(part for part in media_evidence_parts if part.strip())[:12000]
        if not media_evidence:
            attempted.append({
                "source_post_id": post.get("source_post_id", ""),
                "media_asset_id": str(media.get("media_asset_id") or media.get("source_post_media_id") or ""),
                "blocked_reasons": ["media_content_understanding_empty"],
                "quarantined": False,
            })
            continue
        grounded = caption_service.generate(
            bundle,
            account_id=account_id,
            recent_posts=recent_posts,
            transcript_excerpt=media_evidence,
        )
        text = str(grounded.get("public_post_text", ""))
        validation = final_public_post_validator(text, account_id)
        alignment = grounded.get("semantic_alignment", {})
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
            "alignment_status": alignment.get("status", "BLOCKED"),
            "final_alignment_score": alignment.get("final_alignment_score", 0),
            "main_claim_coverage": alignment.get("main_claim_coverage", 0),
            "unsupported_claim_count": alignment.get("unsupported_claim_count", 1),
            "source_copy_similarity": alignment.get("source_copy_similarity", 1),
            "recent_post_similarity": alignment.get("recent_post_similarity", 1),
        })
        ready = grounded.get("status") == "PASS" and validation["status"] == "PASS" and validator["status"] == "PASS"
        blocked_reasons = (
            list(grounded.get("blocked_reasons", []))
            + list(validation.get("blocked_reasons", []))
            + list(validator.get("blocked_reasons", []))
        )
        if apply:
            _record_caption_attempt(client, post=post, account_id=account_id, grounded=grounded)
        if ready:
            return {
                "status": "WILL_APPLY" if apply else "PLAN_ONLY",
                "account_id": account_id, "slot_id": slot_id, "manual_e2e_proof": manual_e2e_proof, "source_post": post, "source_post_media": media,
                "source_post_id": post["source_post_id"], "media_asset_id": asset_id, "public_post_text": text,
                "media_asset_ids": carousel_asset_ids, "media_urls": carousel_urls, "media_types": carousel_types,
                "today_post_count": len(today_posts), "today_direct_media_post_count": len(direct_today),
                "daily_post_cap": daily_cap, "direct_media_daily_post_cap": direct_cap,
                "public_post_preview": public_preview(text), "final_public_post_validator": validation["status"],
                "internal_analysis": grounded.get("internal_analysis", {}),
                "claim_support": grounded.get("claim_support", []),
                "caption_provider": grounded.get("provider_name", ""),
                "caption_provider_version": grounded.get("provider_version", ""),
                "semantic_alignment": alignment,
                "media_validator": validator["status"], "would_post": bool(apply and not prepare_only),
                "prepare_only": prepare_only,
                "candidate_attempt_count": len(attempted) + 1,
                "skipped_candidate_attempts": attempted,
                "blocked_reasons": [],
            }
        failure_reason = "|".join(sorted(set(str(reason) for reason in blocked_reasons if reason))) or "caption_or_alignment_blocked"
        state = _record_candidate_failure(
            client, post=post, media=media, account_id=account_id, reason=failure_reason,
        ) if apply else register_failure(media, failure_reason)
        attempted.append({
            "source_post_id": post.get("source_post_id", ""),
            "media_asset_id": asset_id,
            "failure_signature": state.get("failure_signature", ""),
            "same_failure_count": state.get("same_failure_count", "0"),
            "quarantined": is_quarantined(state),
            "blocked_reasons": blocked_reasons[:10],
        })
    return {
        "status": "BLOCKED",
        "account_id": account_id,
        "slot_id": slot_id,
        "manual_e2e_proof": manual_e2e_proof,
        "would_post": False,
        "candidate_attempt_count": len(attempted),
        "skipped_candidate_attempts": attempted,
        "blocked_reasons": (reasons + [reason for row in attempted for reason in row.get("blocked_reasons", [])])[:30],
    }


def _build_queue(plan: dict[str, Any]) -> dict[str, Any]:
    post, media = plan["source_post"], plan["source_post_media"]
    queue_id = f"direct_media_{business_date().replace('-', '')}_{plan['account_id']}_{post['source_post_id']}_{plan['media_asset_id']}"
    return {
        "queue_id": queue_id, "account_id": plan["account_id"], "target_account_id": plan["account_id"], "platform": "threads",
        "priority": "1", "status": "READY", "auto_publish": "true", "generation_mode": "direct_reference_media",
        "slot_id": plan.get("slot_id", ""), "business_date_jst": business_date(),
        "source_post_id": post["source_post_id"], "source_id": post.get("source_id", ""), "source_url": post.get("post_url", ""),
        "media_asset_id": plan["media_asset_id"], "media_url": media["storage_url"],
        "media_asset_ids_json": json.dumps(plan.get("media_asset_ids", [])),
        "media_urls_json": json.dumps(plan.get("media_urls", [])),
        "media_types_json": json.dumps(plan.get("media_types", [])),
        "media_status": "UPLOADED", "media_required": "true", "media_type": media.get("media_type", "video"),
        "media_origin": "direct_reference", "duration_seconds": media.get("duration_seconds", ""),
        "aspect_ratio": media.get("aspect_ratio", ""), "rights_status": post.get("rights_status", ""), "permission_status": post.get("permission_status", ""),
        "public_post_text": plan["public_post_text"], "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS",
        "caption_provider": plan.get("caption_provider", ""),
        "caption_provider_version": plan.get("caption_provider_version", ""),
        "alignment_status": plan.get("semantic_alignment", {}).get("status", "BLOCKED"),
        "final_alignment_score": plan.get("semantic_alignment", {}).get("final_alignment_score", ""),
        "main_claim_coverage": plan.get("semantic_alignment", {}).get("main_claim_coverage", ""),
        "unsupported_claim_count": plan.get("semantic_alignment", {}).get("unsupported_claim_count", ""),
        "source_copy_similarity": plan.get("semantic_alignment", {}).get("source_copy_similarity", ""),
        "recent_post_similarity": plan.get("semantic_alignment", {}).get("recent_post_similarity", ""),
        "claim_support_json": json.dumps(plan.get("claim_support", []), ensure_ascii=False),
        "content_hash": post.get("content_hash", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def prepare(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    """Persist one validated READY item without invoking a publisher."""
    queue = _build_queue(plan)
    existing = {str(row.get("queue_id", "")) for row in _records(client, "queue")}
    if queue["queue_id"] not in existing:
        append_row(client, "queue", queue)
        _invalidate_records(client, "queue")
    return {
        **plan,
        "status": "PREPARED",
        "queue_id": queue["queue_id"],
        "already_prepared": queue["queue_id"] in existing,
        "would_post": False,
    }


def execute(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    if plan.get("slot_id") and existing_slot_status(client, plan["account_id"], plan["slot_id"]) in POSTED_SLOT_STATUSES:
        return {**plan, "status": "SKIPPED", "reason": "slot_already_posted", "would_post": False}
    post = plan["source_post"]
    queue = _build_queue(plan)
    queue_id = queue["queue_id"]
    if queue_id not in {str(row.get("queue_id", "")) for row in _records(client, "queue")}:
        append_row(client, "queue", queue)
        _invalidate_records(client, "queue")
    result = process_one(client, queue, dry_run=False, confirm_real_post=True)
    posted = str(result.get("status", "")) in {"POSTED", "POSTED_SAVE_FAILED"}
    if plan.get("slot_id"):
        slot = build_slot_run(plan["account_id"], plan["slot_id"], status="POSTED_PRIMARY" if posted else "FAILED", actual_post_type="direct_reference_media", fallback_level=0, source_post_id=post["source_post_id"], media_asset_id=plan["media_asset_id"], queue_id=queue_id, result_id=result.get("result_id", ""), post_url=result.get("post_url", ""), actual_posted_at=datetime.now(timezone.utc).isoformat() if posted else "", no_post_reason="" if posted else str(result.get("reason", result.get("status", "failed"))))
        slot_result = upsert_slot_run(client, slot)
    else:
        slot_result = {"status": "SKIPPED", "reason": "manual_e2e_proof_does_not_claim_scheduled_slot"}
    return {**plan, "status": result.get("status", "FAILED"), "queue_id": queue_id, "post_result": result, "content_slot_run": slot_result, "would_post": False}


def dispatch_ready(
    client: SheetsClient,
    account_id: str,
    slot_id: str,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Post only precomputed READY inventory for this canonical slot."""
    if existing_slot_status(client, account_id, slot_id) in POSTED_SLOT_STATUSES:
        return {"status": "SKIPPED", "reason": "slot_already_posted", "account_id": account_id, "slot_id": slot_id, "would_post": False}
    target_date = business_date()
    candidates = [
        row for row in _records(client, "queue")
        if str(row.get("account_id") or row.get("target_account_id") or "") == account_id
        and str(row.get("platform", "")).lower() == "threads"
        and str(row.get("status", "")).upper() == "READY"
        and str(row.get("generation_mode", "")) == "direct_reference_media"
        and str(row.get("slot_id", "")) == slot_id
        and str(row.get("business_date_jst", "")) == target_date
    ]
    candidates.sort(key=lambda row: (int(str(row.get("priority", "100") or "100")), str(row.get("created_at", ""))))
    if not candidates:
        return {"status": "NO_POST", "reason": "NO_READY_DIRECT_MEDIA", "account_id": account_id, "slot_id": slot_id, "would_post": False}
    attempts: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    for queue in candidates:
        preview = process_one(client, queue, dry_run=True, confirm_real_post=False)
        attempts.append({"phase": "preflight", "queue_id": queue.get("queue_id", ""), "status": preview.get("status", ""), "reason": preview.get("reason", "")})
        if str(preview.get("status", "")) == "DRY_RUN":
            selected = queue
            break
    if not selected:
        return {"status": "NO_POST", "reason": "READY_DIRECT_MEDIA_BLOCKED_ALL", "account_id": account_id, "slot_id": slot_id, "attempts": attempts, "would_post": False}
    if dry_run:
        return {"status": "DRY_RUN", "account_id": account_id, "slot_id": slot_id, "selected_queue_id": selected.get("queue_id", ""), "attempts": attempts, "would_post": False}
    claim = claim_slot_run(client, account_id, slot_id)
    if claim.get("status") != "CLAIMED":
        return {
            "status": "SKIPPED",
            "reason": claim.get("reason", "slot_not_claimed"),
            "account_id": account_id,
            "slot_id": slot_id,
            "would_post": False,
        }
    result = process_one(client, selected, dry_run=False, confirm_real_post=True)
    attempts.append({"phase": "publish", "queue_id": selected.get("queue_id", ""), "status": result.get("status", ""), "reason": result.get("reason", "")})
    posted = str(result.get("status", "")) in {"POSTED", "POSTED_SAVE_FAILED"}
    if posted:
        slot = build_slot_run(
            account_id, slot_id, status="POSTED_PRIMARY", actual_post_type="direct_reference_media",
            fallback_level=0, source_post_id=selected.get("source_post_id", ""),
            media_asset_id=selected.get("media_asset_id", ""), queue_id=selected.get("queue_id", ""),
            result_id=result.get("result_id", ""), post_url=result.get("post_url", ""),
            actual_posted_at=datetime.now(timezone.utc).isoformat(),
            no_post_reason="" if result.get("status") == "POSTED" else "POSTED_SAVE_FAILED",
        )
        return {"status": result.get("status", "POSTED"), "account_id": account_id, "slot_id": slot_id, "selected_queue_id": selected.get("queue_id", ""), "attempts": attempts, "content_slot_run": upsert_slot_run(client, slot), "post_result": result, "would_post": False}
    return {"status": result.get("status", "FAILED"), "account_id": account_id, "slot_id": slot_id, "selected_queue_id": selected.get("queue_id", ""), "attempts": attempts, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="post an explicitly permitted direct-reference media slot")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--slot-id", default="")
    parser.add_argument("--manual-e2e-proof", action="store_true", help="workflow_dispatch-only proof; never claims a scheduled slot")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-direct-media", action="store_true")
    parser.add_argument("--fallback-to-text", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true", help="create READY inventory; never call Threads")
    mode.add_argument("--post-ready", action="store_true", help="dispatch precomputed READY inventory only")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    client = None
    if args.use_sheets:
        cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    publish_mode = not args.prepare_only
    if args.apply and not args.confirm_direct_media:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["apply requires --confirm-direct-media"]}, ensure_ascii=False)); return 1
    if args.apply and publish_mode and (not _true(os.environ.get("PUBLISH_ENABLED")) or not _true(os.environ.get("ALLOW_REAL_THREADS_POST")) or not _true(os.environ.get("ALLOW_MEDIA_POSTS")) or not _true(os.environ.get("ALLOW_REAL_THREADS_VIDEO_POST"))):
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["apply requires confirmation and all Threads media gates"]}, ensure_ascii=False)); return 1
    if not args.slot_id and not args.manual_e2e_proof:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["--slot-id or --manual-e2e-proof is required"]}, ensure_ascii=False)); return 1
    if args.post_ready:
        plan = dispatch_ready(client, args.account_id, args.slot_id, dry_run=not args.apply) if client else {"status": "PLAN_ONLY", "account_id": args.account_id, "slot_id": args.slot_id, "would_post": False}
    else:
        plan = build_plan(
            args.account_id, args.slot_id, client, apply=args.apply,
            manual_e2e_proof=args.manual_e2e_proof, prepare_only=args.prepare_only,
        )
        if args.apply and client and plan.get("status") == "WILL_APPLY":
            plan = prepare(plan, client) if args.prepare_only else execute(plan, client)
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
