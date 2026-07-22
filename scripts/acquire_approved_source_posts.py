#!/usr/bin/env python3
"""Acquire owner-attested source posts through the configured adapter router.

This is the only discovery writer used by the direct-reference workflows.  It
stores a post and every resolved media item under the same ``source_post_id``;
the writer is intentionally idempotent and never downloads, uploads or posts.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.factory import build_provider_registry, build_router
from acquisition.models import NormalizedSourcePost, validate_source_post
from acquisition.router import BackendFailure
from config_loader import get_config
from media_source_policy import media_usage_mode
from media_growth_schemas import build_source_video
from sheets_client import TAB_DEFINITIONS, SheetsClient
from transcription.sheets_limits import bounded_cell, normalize_transcript_row

MEDIA_PLATFORMS = {"threads", "youtube", "tiktok"}
BLOCKED_ACCOUNTS = {"beauty_account"}


def truthy(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def source_platform(source: dict[str, Any]) -> str:
    return str(source.get("source_platform") or source.get("platform") or "").lower()


def account_for(source: dict[str, Any]) -> str:
    return str((source.get("target_account_ids") or [source.get("target_account_id")])[0] or "")


def capability_for(platform: str) -> str:
    return {
        "threads": "threads.profile_posts",
        "tiktok": "tiktok.profile_posts",
        "youtube": "youtube.channel_videos",
    }[platform]


def selected_sources(account_id: str, platform_filter: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    data = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))
    selected: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for source in data.get("sources", []):
        platform = source_platform(source)
        account = account_for(source)
        if account_id != "all" and account != account_id:
            continue
        if platform_filter != "all" and platform != platform_filter:
            continue
        if platform not in MEDIA_PLATFORMS or account in BLOCKED_ACCOUNTS or platform == "x":
            continue
        if not truthy(source.get("active")):
            continue
        # The owner-attested permission ledger is the runtime authority.  The
        # repository mapping merely limits which active sources can be planned.
        if media_usage_mode(source) not in {"direct_media_reuse", "direct_and_clip"}:
            blocked.append({"source_id": str(source.get("source_id", "")), "reason": "usage_mode_not_media_approved"})
            continue
        selected.append(source)
    return selected, blocked


def ledger_permission(client: SheetsClient, source_id: str) -> dict[str, Any] | None:
    client._ensure_tab("media_permissions", TAB_DEFINITIONS["media_permissions"])
    rows = client._call_with_rate_limit_retry(
        "get_all_records:media_permissions:acquisition",
        lambda: client._ws("media_permissions").get_all_records(),
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        if str(row.get("source_id", "")) != source_id or truthy(row.get("revoked")):
            continue
        expires_at = str(row.get("expires_at", "")).strip()
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                expiry = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if expiry <= now:
                continue
        if not str(row.get("evidence_type", "")).strip() or not str(row.get("evidence_reference", "")).strip():
            continue
        if all(truthy(row.get(name)) for name in (
            "allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption",
        )):
            normalized = dict(row)
            normalized["rights_status"] = str(row.get("rights_status") or "approved_creator_clip")
            normalized["permission_status"] = "approved"
            return normalized
    return None


def ledger_allows(client: SheetsClient, source_id: str) -> bool:
    return ledger_permission(client, source_id) is not None


def _headers(client: SheetsClient, logical: str) -> tuple[Any, list[str], list[dict[str, Any]]]:
    ws = client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    headers = client._call_with_rate_limit_retry(f"headers:{logical}:acquisition", lambda: ws.row_values(1))
    rows = client._call_with_rate_limit_retry(f"rows:{logical}:acquisition", lambda: ws.get_all_records())
    return ws, headers, rows


def _append(client: SheetsClient, ws: Any, headers: list[str], row: dict[str, Any], label: str) -> None:
    client._call_with_rate_limit_retry(
        label,
        lambda: ws.append_row(
            [bounded_cell(row.get(header, "")) for header in headers],
            value_input_option="USER_ENTERED",
        ),
    )


def persist(
    client: SheetsClient,
    posts: list[NormalizedSourcePost],
    policy_by_source: dict[str, dict[str, str]] | None = None,
) -> dict[str, int]:
    posts_ws, post_headers, existing_posts = _headers(client, "source_posts")
    media_ws, media_headers, existing_media = _headers(client, "source_post_media")
    canonical_seen = {str(row.get("canonical_post_url", "")) for row in existing_posts}
    post_seen = {str(row.get("source_post_id", "")) for row in existing_posts}
    media_seen = {str(row.get("source_post_media_id", "")) for row in existing_media}
    saved_posts = saved_media = duplicates = invalid = 0
    for post in posts:
        if validate_source_post(post):
            invalid += 1
            continue
        duplicate = post.source_post_id in post_seen or post.canonical_post_url in canonical_seen
        if duplicate:
            duplicates += 1
        else:
            policy = (policy_by_source or {}).get(post.source_id, {})
            _append(client, posts_ws, post_headers, post.to_sheet_row(
                rights_status=policy.get("rights_status", "unknown"),
                permission_status=policy.get("permission_status", "unknown"),
            ), "append:source_posts:acquisition")
            saved_posts += 1
            post_seen.add(post.source_post_id)
            canonical_seen.add(post.canonical_post_url)
        for item in post.media_items:
            if item.source_post_media_id in media_seen:
                continue
            policy = (policy_by_source or {}).get(post.source_id, {})
            _append(client, media_ws, media_headers, item.to_sheet_row(
                rights_status=policy.get("rights_status", "unknown"),
                permission_status=policy.get("permission_status", "unknown"),
            ), "append:source_post_media:acquisition")
            saved_media += 1
            media_seen.add(item.source_post_media_id)
    return {"saved_source_posts": saved_posts, "saved_source_post_media": saved_media,
            "duplicate_source_posts": duplicates, "invalid_source_posts": invalid}


def _provider_event(
    source: dict[str, Any],
    post: NormalizedSourcePost,
    capability: str,
    outcome: Any,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "provider_run_id": f"pr_{post.source_post_id}_{capability.replace('.', '_')}_{int(now.timestamp() * 1000000)}",
        "source_id": post.source_id,
        "source_post_id": post.source_post_id,
        "source_video_id": "",
        "platform": post.platform,
        "capability": capability,
        "provider_name": outcome.provider_name,
        "provider_version": outcome.provider_version,
        "status": outcome.status,
        "reason": str(outcome.reason)[:240],
        "retryable": str(bool(outcome.retryable)).lower(),
        "duration_ms": str(outcome.duration_ms),
        "attempt_count": "1",
        "created_at": now.isoformat(),
    }


def _route_provider_event(
    source: dict[str, Any],
    *,
    platform: str,
    capability: str,
    provider_name: str,
    provider_version: str,
    status: str,
    reason: str = "",
    retryable: bool = False,
    attempt_count: int = 1,
) -> dict[str, Any]:
    """Record profile routing like every other provider invocation."""
    now = datetime.now(timezone.utc)
    return {
        "provider_run_id": f"pr_{source.get('source_id', '')}_{capability.replace('.', '_')}_{int(now.timestamp() * 1000000)}",
        "source_id": source.get("source_id", ""), "source_post_id": "", "source_video_id": "",
        "platform": platform, "capability": capability,
        "provider_name": provider_name, "provider_version": provider_version,
        "status": status, "reason": str(reason)[:240],
        "retryable": str(bool(retryable)).lower(), "duration_ms": "",
        "attempt_count": str(max(1, attempt_count)), "created_at": now.isoformat(),
    }


def enrich_posts(
    source: dict[str, Any],
    posts: list[NormalizedSourcePost],
    permission: dict[str, Any],
    providers: dict[str, object],
) -> tuple[list[NormalizedSourcePost], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    enriched: list[NormalizedSourcePost] = []
    source_videos: list[dict[str, Any]] = []
    transcripts: list[dict[str, Any]] = []
    provider_runs: list[dict[str, Any]] = []
    for original in posts:
        post = original
        if post.platform in {"youtube", "tiktok"}:
            detail = providers["yt_dlp_post_detail"].fetch_post_detail(post)
            provider_runs.append(_provider_event(source, post, "video.post_detail", detail))
            if detail.ok and detail.data:
                post = detail.data

        comment_provider_name = {
            "youtube": "youtube_comment_downloader",
            "threads": "threads_public_comments",
        }.get(post.platform)
        if comment_provider_name:
            comments = providers[comment_provider_name].fetch_comments(post, limit=30)
            provider_runs.append(_provider_event(source, post, f"{post.platform}.comments", comments))
            if comments.ok:
                post = replace(
                    post,
                    comments=tuple(comments.data or []),
                    detail_status="COMPLETE" if comments.status == "PASS" else post.detail_status,
                )

        if post.platform in {"youtube", "tiktok"}:
            duration = next((item.duration_seconds for item in post.media_items if item.duration_seconds), "")
            source_video = build_source_video(
                source,
                video_url=post.canonical_post_url,
                title=post.original_post_text.splitlines()[0][:240] if post.original_post_text else "",
                duration_seconds=float(duration or 0),
                description=post.original_post_text,
                discovery_status="DISCOVERED",
            )
            source_video.update({
                "published_at": post.published_at,
                "view_count": post.engagement.get("view_count", ""),
                "like_count": post.engagement.get("like_count", ""),
                "comment_count": post.engagement.get("comment_count", ""),
                "rights_status": str(permission.get("rights_status") or "approved_creator_clip"),
                "permission_status": str(permission.get("permission_status") or "approved"),
                "content_hash": post.content_hash,
            })
            source_videos.append(source_video)
            if post.platform == "youtube" and truthy(permission.get("allow_transcription")):
                transcript = providers["youtube_transcript_api"].fetch_transcript(post)
                event = _provider_event(source, post, "youtube.transcript", transcript)
                event["source_video_id"] = source_video["source_video_id"]
                provider_runs.append(event)
                payload = transcript.data or {}
                transcripts.append(normalize_transcript_row({
                    "transcript_id": f"tr_{source_video['source_video_id']}",
                    "account_id": post.target_account_id,
                    "reference_post_id": post.source_post_id,
                    "source_video_id": source_video["source_video_id"],
                    "video_id": post.external_post_id,
                    "source_id": post.source_id,
                    "source_platform": post.platform,
                    "video_url": post.canonical_post_url,
                    "transcription_provider": transcript.provider_name,
                    "transcription_status": "DONE" if transcript.status == "PASS" else transcript.status,
                    "duration_seconds": duration,
                    "transcript_text": str(payload.get("text", "")),
                    "segments_json": json.dumps(payload.get("segments", []), ensure_ascii=False),
                    "language": str(payload.get("language", "")),
                    "processed_minutes": "",
                    "transcription_scope": "official_caption_only",
                    "processed_duration_seconds": duration,
                    "transcript_hash": stable_hash_text(str(payload.get("text", ""))),
                    "chunk_count": str(max(1, len(str(payload.get("text", ""))) // 1000 + 1)) if payload.get("text") else "0",
                    "error": "" if transcript.ok else transcript.reason,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }))
        enriched.append(post)
    return enriched, source_videos, transcripts, provider_runs


def stable_hash_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest() if text else ""


def persist_auxiliary(
    client: SheetsClient,
    logical: str,
    rows: list[dict[str, Any]],
    *,
    identity_fields: tuple[str, ...],
) -> int:
    if not rows:
        return 0
    ws, headers, existing = _headers(client, logical)
    seen = {tuple(str(row.get(field, "")) for field in identity_fields) for row in existing}
    saved = 0
    for row in rows:
        identity = tuple(str(row.get(field, "")) for field in identity_fields)
        if identity in seen:
            continue
        _append(client, ws, headers, row, f"append:{logical}:acquisition")
        seen.add(identity)
        saved += 1
    return saved


def persist_observability(client: SheetsClient, results: list[dict[str, Any]]) -> None:
    health_ws, health_headers, _ = _headers(client, "backend_health")
    history_ws, history_headers, _ = _headers(client, "backend_routing_history")
    now = datetime.now(timezone.utc).isoformat()
    for result in results:
        name = str(result.get("selected_backend") or result.get("primary_backend") or "")
        if name:
            _append(client, health_ws, health_headers, {
                "backend_health_id": f"bh_{name}_{int(datetime.now().timestamp() * 1000000)}",
                "backend_name": name, "platform": result.get("platform", ""), "capability": result.get("capability", ""),
                "status": result.get("status", ""), "last_success_at": now if result.get("status") == "PASS" else "",
                "last_failure_at": now if result.get("status") != "PASS" else "", "consecutive_failures": result.get("consecutive_failures", "0"),
                "cooldown_until": result.get("cooldown_until", ""), "average_duration_ms": "",
                "failure_reason": result.get("reason", "")[:240], "selected_as_primary": str(not result.get("fallback_used", False)).lower(), "updated_at": now,
            }, "append:backend_health:acquisition")
        _append(client, history_ws, history_headers, {
            "routing_event_id": f"brh_{result.get('source_id', '')}_{int(datetime.now().timestamp() * 1000000)}",
            "source_id": result.get("source_id", ""), "platform": result.get("platform", ""), "capability": result.get("capability", ""),
            "primary_backend": result.get("primary_backend", ""), "selected_backend": result.get("selected_backend", ""),
            "fallback_used": str(result.get("fallback_used", False)).lower(),
            "shadow_backend_counts": json.dumps(result.get("shadow_backend_counts", {}), sort_keys=True),
            "status": result.get("status", ""), "reason": result.get("reason", "")[:240],
            "selected_backend_version": result.get("selected_backend_version", ""),
            "attempt_count": str(result.get("attempt_count") or 1),
            "retryable": str(bool(result.get("retryable", result.get("status") != "PASS"))).lower(),
            "created_at": now,
        }, "append:backend_routing_history:acquisition")


def run(account_id: str, platform_filter: str, max_posts: int, *, apply: bool, shadow: bool) -> dict[str, Any]:
    sources, blocked = selected_sources(account_id, platform_filter)
    result: dict[str, Any] = {
        "status": "PLAN_ONLY", "account_id": account_id, "selected_source_count": len(sources),
        "blocked_sources": blocked, "network_fetch": False, "would_save_source_posts": False,
        "source_results": [], "discovered_post_count": 0, "media_item_count": 0,
    }
    if not apply:
        result["source_results"] = [{"source_id": source["source_id"], "platform": source_platform(source),
                                     "capability": capability_for(source_platform(source)), "status": "PLAN_ONLY"} for source in sources]
        return result
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    router = build_router()
    providers = build_provider_registry()
    posts: list[NormalizedSourcePost] = []
    source_video_rows: list[dict[str, Any]] = []
    transcript_rows: list[dict[str, Any]] = []
    provider_run_rows: list[dict[str, Any]] = []
    policy_by_source: dict[str, dict[str, str]] = {}
    observability: list[dict[str, Any]] = []
    for source in sources:
        platform = source_platform(source)
        capability = capability_for(platform)
        base = {"source_id": str(source["source_id"]), "platform": platform, "capability": capability,
                "primary_backend": router.routes[capability].primary}
        permission = ledger_permission(client, str(source["source_id"]))
        if not permission:
            result["source_results"].append({**base, "status": "BLOCKED", "reason": "active_permission_ledger_missing"})
            observability.append({**base, "status": "BLOCKED", "reason": "active_permission_ledger_missing"})
            continue
        try:
            routed = router.route(capability, source, limit=max(1, min(max_posts, 10)), shadow=shadow)
            selected_adapter = router.adapters.get(routed.backend_name)
            provider_run_rows.append(_route_provider_event(
                source,
                platform=platform,
                capability=capability,
                provider_name=routed.backend_name,
                provider_version=str(getattr(selected_adapter, "backend_version", "unknown")),
                status="PASS",
                attempt_count=len(routed.attempted_backends),
            ))
            valid = [post for post in routed.posts if not validate_source_post(post)]
            valid, videos, transcripts, provider_events = enrich_posts(source, valid, permission, providers)
            posts.extend(valid)
            source_video_rows.extend(videos)
            transcript_rows.extend(transcripts)
            provider_run_rows.extend(provider_events)
            policy_by_source[str(source["source_id"])] = {
                "rights_status": str(permission.get("rights_status") or "approved_creator_clip"),
                "permission_status": str(permission.get("permission_status") or "approved"),
            }
            item = {**base, "status": "PASS", "selected_backend": routed.backend_name,
                    "selected_backend_version": str(getattr(selected_adapter, "backend_version", "unknown")),
                    "attempt_count": len(routed.attempted_backends), "retryable": False,
                    "fallback_used": routed.fallback_used, "post_count": len(valid),
                    "shadow_backend_counts": routed.shadow_results}
        except BackendFailure as exc:
            primary_adapter = router.adapters.get(base["primary_backend"])
            attempts = 1 + len(router.routes[capability].fallbacks)
            provider_run_rows.append(_route_provider_event(
                source,
                platform=platform,
                capability=capability,
                provider_name=base["primary_backend"],
                provider_version=str(getattr(primary_adapter, "backend_version", "unknown")),
                status="FAILED",
                reason=str(exc),
                retryable=True,
                attempt_count=attempts,
            ))
            item = {**base, "status": "FAILED", "reason": str(exc)[:240], "attempt_count": attempts, "retryable": True}
        result["source_results"].append(item)
        observability.append(item)
    persisted = persist(client, posts, policy_by_source)
    persisted["saved_source_videos"] = persist_auxiliary(
        client, "source_videos", source_video_rows, identity_fields=("source_video_id",),
    )
    persisted["saved_video_transcripts"] = persist_auxiliary(
        client, "video_transcripts", transcript_rows, identity_fields=("transcript_id",),
    )
    persisted["saved_provider_runs"] = persist_auxiliary(
        client, "provider_runs", provider_run_rows, identity_fields=("provider_run_id",),
    )
    persist_observability(client, observability)
    result.update(persisted)
    result.update({"status": "APPLIED", "network_fetch": True, "discovered_post_count": len(posts),
                   "media_item_count": sum(post.media_count for post in posts), "would_save_source_posts": bool(posts)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="acquire owner-approved source posts via primary/fallback adapters")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager"])
    parser.add_argument("--platform", default="all", choices=["all", "threads", "youtube", "tiktok"])
    parser.add_argument("--max-posts", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-acquisition", action="store_true")
    parser.add_argument("--shadow", action="store_true", help="run configured analysis-only shadow adapters when installed")
    args = parser.parse_args()
    if args.apply and not args.confirm_acquisition:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-acquisition"})); return 1
    if args.dry_run and args.apply:
        print(json.dumps({"status": "BLOCKED", "reason": "choose --dry-run or --apply"})); return 1
    outcome = run(args.account_id, args.platform, args.max_posts, apply=args.apply, shadow=args.shadow)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0 if outcome["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
