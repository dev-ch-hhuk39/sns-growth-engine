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

from acquisition.factory import build_provider_registry, build_router  # noqa: E402
from acquisition.failures import classify_failure  # noqa: E402
from acquisition.models import NormalizedSourcePost, validate_source_post  # noqa: E402
from acquisition.router import BackendFailure  # noqa: E402
from config_loader import get_config  # noqa: E402
from generation.media_platform_policy import (  # noqa: E402
    DEFERRED_REFERENCE_PLATFORMS,
    DEFERRED_REFERENCE_REASON,
    DEFERRED_REFERENCE_STATUS,
    is_retired_source,
)
from media_source_policy import media_usage_mode  # noqa: E402
from media.permission_ledger import evaluate_permission  # noqa: E402
from media_growth_schemas import build_source_video  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402
from transcription.sheets_limits import (  # noqa: E402
    bounded_cell,
    normalize_transcript_row,
)
from source_discovery_policy import (  # noqa: E402
    build_state_update,
    plan_source_scan,
    select_unique_candidates,
)
from reference.source_registry import load_registry  # noqa: E402

MEDIA_PLATFORMS = {"threads", "youtube", "tiktok", "x"}
BLOCKED_ACCOUNTS: set[str] = set()


def beauty_voice_reference_policy() -> tuple[set[str], dict[str, Any]]:
    path = ROOT / "config/beauty_voice_profile.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    return (
        {str(value) for value in profile.get("voice_reference_source_ids", [])},
        dict(profile.get("bounded_reference_collection") or {}),
    )


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
        "x": "x.profile_posts",
    }[platform]


def classify_external_failure(platform: str, reason: str) -> str:
    """Map bounded backend failures to operator-actionable external states."""
    return classify_failure(platform, reason).value


def selected_sources(
    account_id: str, platform_filter: str, *, reference_only: bool = False
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    voice_source_ids, voice_policy = beauty_voice_reference_policy()
    voice_collection_enabled = truthy(voice_policy.get("enabled"))
    selected: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for source in load_registry():
        platform = source_platform(source)
        account = account_for(source)
        is_beauty_voice_source = (
            account == "beauty_account"
            and str(source.get("source_id") or "") in voice_source_ids
            and voice_collection_enabled
        )
        if account_id != "all" and account != account_id:
            continue
        if platform_filter != "all" and platform != platform_filter:
            continue
        if is_retired_source(source):
            blocked.append(
                {
                    "source_id": str(source.get("source_id", "")),
                    "reason": "source_retired_from_runtime_selection",
                }
            )
            continue
        if platform not in MEDIA_PLATFORMS or account in BLOCKED_ACCOUNTS:
            continue
        if not truthy(source.get("active")) and not is_beauty_voice_source:
            continue
        if platform in DEFERRED_REFERENCE_PLATFORMS:
            blocked.append(
                {
                    "source_id": str(source.get("source_id", "")),
                    "platform": platform,
                    "status": DEFERRED_REFERENCE_STATUS,
                    "reason": DEFERRED_REFERENCE_REASON,
                }
            )
            continue
        if platform == "x" and not (
            truthy(source.get("x_read_only"))
            or (is_beauty_voice_source and truthy(voice_policy.get("x_read_only")))
        ):
            blocked.append({"source_id": str(source.get("source_id", "")), "reason": "x_read_only_not_approved"})
            continue
        if reference_only:
            # Reference acquisition never grants reuse rights. It is limited
            # to sources that were explicitly enabled for bounded fetching.
            if truthy(source.get("fetch_enabled")) or is_beauty_voice_source:
                if is_beauty_voice_source:
                    source = {
                        **source,
                        # Runtime-only adapter flags. The Voice Corpus policy
                        # is the authority for these eight IDs; no permission
                        # or media-reuse fields are promoted.
                        "active": True,
                        "fetch_enabled": True,
                        "allow_network_fetch": True,
                        "x_read_only": platform == "x",
                    }
                selected.append(source)
            continue
        if platform == "x" and source.get("x_video_candidate_enabled") is not True:
            blocked.append(
                {
                    "source_id": str(source.get("source_id", "")),
                    "reason": "x_source_not_editorially_selected_for_video",
                }
            )
            continue
        # The owner-attested permission ledger is the runtime authority.  The
        # repository mapping merely limits which active sources can be planned.
        if media_usage_mode(source) not in {"direct_media_reuse", "direct_and_clip"}:
            blocked.append(
                {
                    "source_id": str(source.get("source_id", "")),
                    "reason": "usage_mode_not_media_approved",
                }
            )
            continue
        selected.append(source)
    return selected, blocked


def post_matches_registered_author(post: NormalizedSourcePost, source: dict[str, Any]) -> bool:
    if not truthy(source.get("original_author_match_required")):
        return True
    expected = str(source.get("source_handle") or source.get("author_handle") or "").strip().lower().lstrip("@")
    actual = str(post.author_handle or "").strip().lower().lstrip("@")
    return bool(expected and actual and expected == actual)


def reference_only_permission(source: dict[str, Any]) -> dict[str, str]:
    """Policy for source text and ordered media metadata, never media reuse."""
    return {
        "rights_status": str(
            source.get("rights_status")
            or source.get("rights_policy")
            or "reference_only"
        ),
        "permission_status": "reference_only",
    }


def ledger_permission(
    client: SheetsClient,
    source_id: str,
    *,
    account_id: str = "",
    source_handle: str = "",
) -> dict[str, Any] | None:
    client._ensure_tab("media_permissions", TAB_DEFINITIONS["media_permissions"])
    rows = client._call_with_rate_limit_retry(
        "get_all_records:media_permissions:acquisition",
        lambda: client._ws("media_permissions").get_all_records(),
    )
    decision = evaluate_permission(
        rows,
        source_id,
        account_id=account_id,
        source_handle=source_handle,
        required_flags=(
            "allow_download",
            "allow_cloudinary_storage",
            "allow_original_repost",
            "allow_new_caption",
        ),
    )
    return dict(decision["row"]) if decision["allowed"] else None


def ledger_allows(client: SheetsClient, source_id: str, *, account_id: str = "") -> bool:
    return ledger_permission(client, source_id, account_id=account_id) is not None


def _headers(client: SheetsClient, logical: str) -> tuple[Any, list[str], list[dict[str, Any]]]:
    ws = client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    headers = client._call_with_rate_limit_retry(
        f"headers:{logical}:acquisition", lambda: ws.row_values(1)
    )
    rows = client._call_with_rate_limit_retry(
        f"rows:{logical}:acquisition", lambda: ws.get_all_records()
    )
    return ws, headers, rows


def _append(
    client: SheetsClient, ws: Any, headers: list[str], row: dict[str, Any], label: str
) -> None:
    client._call_with_rate_limit_retry(
        label,
        lambda: ws.append_row(
            [bounded_cell(row.get(header, "")) for header in headers],
            value_input_option="USER_ENTERED",
        ),
    )


def load_discovery_config() -> dict[str, Any]:
    """Load shared scan policy with post-specific new-item limits."""

    path = ROOT / "config/media_growth_engine.json"

    config = json.loads(path.read_text(encoding="utf-8"))

    config["max_new_videos_per_source_per_run"] = int(
        config.get(
            "max_new_source_posts_per_source_per_run",
            config.get(
                "max_new_videos_per_source_per_run",
                3,
            ),
        )
    )

    config["max_total_new_videos_per_run"] = int(
        config.get(
            "max_total_new_source_posts_per_run",
            config.get(
                "max_total_new_videos_per_run",
                12,
            ),
        )
    )

    return config


def _read_sheet_rows(
    client: SheetsClient,
    tab_name: str,
    operation: str,
) -> list[dict[str, Any]]:
    """Read a tab without creating it."""

    try:
        rows = client._call_with_rate_limit_retry(
            operation,
            lambda: client._ws(tab_name).get_all_records(),
        )
    except Exception as exc:
        if type(exc).__name__ == "WorksheetNotFound":
            return []

        raise

    return [dict(row) for row in rows]


def normalize_existing_source_posts(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map source_posts rows to the shared discovery-policy vocabulary."""

    positions: dict[str, int] = {}
    normalized: list[dict[str, Any]] = []

    completed_statuses = {
        "POSTED",
        "USED",
        "CONSUMED",
        "ARCHIVED",
        "COMPLETE",
        "COMPLETED",
        "DONE",
        "PROCESSED",
    }

    for original in rows:
        row = dict(original)

        source_id = str(
            row.get(
                "source_id",
                "",
            )
        )

        positions[source_id] = (
            positions.get(
                source_id,
                0,
            )
            + 1
        )

        account_id = str(
            row.get(
                "target_account_id",
                "",
            )
            or row.get(
                "account_id",
                "",
            )
        )

        processing_status = str(
            row.get(
                "processing_status",
                "",
            )
            or row.get(
                "collection_status",
                "",
            )
        ).upper()

        if row.get("quarantined_at") or row.get("quarantine_reason"):
            post_status = "QUARANTINED"
        elif processing_status in completed_statuses:
            post_status = "POSTED"
        else:
            post_status = "NOT_POSTED"

        normalized.append(
            {
                **row,
                "account_id": account_id,
                "target_account_id": account_id,
                "post_id": str(
                    row.get(
                        "external_post_id",
                        "",
                    )
                    or row.get(
                        "source_post_id",
                        "",
                    )
                ),
                "source_position": int(
                    row.get(
                        "source_position",
                        0,
                    )
                    or positions[source_id]
                ),
                "post_status": post_status,
                "status": post_status,
                "queue_status": ("POSTED" if post_status == "POSTED" else "PENDING"),
                "use_status": ("USED" if post_status == "POSTED" else "UNUSED"),
            }
        )

    return normalized


def load_post_discovery_data(
    client: SheetsClient,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Read existing source posts and post discovery state."""

    source_posts = _read_sheet_rows(
        client,
        "source_posts",
        ("get_all_records:" "source_posts:" "incremental_acquisition"),
    )

    state_rows = _read_sheet_rows(
        client,
        "source_discovery_state",
        ("get_all_records:" "source_discovery_state:" "post_acquisition"),
    )

    return (
        normalize_existing_source_posts(source_posts),
        state_rows,
    )


def source_post_candidate(
    post: NormalizedSourcePost,
    *,
    source_position: int,
) -> dict[str, Any]:
    """Create a policy row while retaining the normalized post object."""

    return {
        "source_id": post.source_id,
        "account_id": post.target_account_id,
        "target_account_id": (post.target_account_id),
        "source_post_id": post.source_post_id,
        "external_post_id": post.external_post_id,
        "post_id": post.external_post_id,
        "canonical_post_url": (post.canonical_post_url),
        "published_at": post.published_at,
        "source_position": source_position,
        "_post": post,
    }


def is_duplicate_source_post(
    candidate: dict[str, Any],
    rows: list[dict[str, Any]],
) -> bool:
    """Deduplicate by parent identity, source post ID, and canonical URL."""

    candidate_source_id = str(
        candidate.get(
            "source_id",
            "",
        )
    )

    candidate_source_post_id = str(
        candidate.get(
            "source_post_id",
            "",
        )
    )

    candidate_external_id = str(
        candidate.get(
            "external_post_id",
            "",
        )
        or candidate.get(
            "post_id",
            "",
        )
    )

    candidate_url = str(
        candidate.get(
            "canonical_post_url",
            "",
        )
    )

    for row in rows:
        row_source_id = str(
            row.get(
                "source_id",
                "",
            )
        )

        row_source_post_id = str(
            row.get(
                "source_post_id",
                "",
            )
        )

        row_external_id = str(
            row.get(
                "external_post_id",
                "",
            )
            or row.get(
                "post_id",
                "",
            )
        )

        row_url = str(
            row.get(
                "canonical_post_url",
                "",
            )
        )

        if candidate_source_post_id and candidate_source_post_id == row_source_post_id:
            return True

        if candidate_url and candidate_url == row_url:
            return True

        if (
            candidate_source_id
            and candidate_external_id
            and candidate_source_id == row_source_id
            and candidate_external_id == row_external_id
        ):
            return True

    return False


def append_discovery_state_to_sheets(
    client: SheetsClient,
    rows: list[dict[str, Any]],
) -> int:
    """Append immutable discovery-state snapshots idempotently."""

    if not rows:
        return 0

    client._ensure_tab(
        "source_discovery_state",
        TAB_DEFINITIONS["source_discovery_state"],
    )

    ws = client._ws("source_discovery_state")

    headers = client._call_with_rate_limit_retry(
        ("row_values:" "source_discovery_state:" "post_acquisition"),
        lambda: ws.row_values(1),
    )

    existing = [
        dict(row)
        for row in client._call_with_rate_limit_retry(
            ("get_all_records:" "source_discovery_state:" "post_acquisition_append"),
            lambda: ws.get_all_records(),
        )
    ]

    existing_keys = {
        (
            str(
                row.get(
                    "state_id",
                    "",
                )
            ),
            str(
                row.get(
                    "last_scan_at",
                    "",
                )
            ),
            str(
                row.get(
                    "updated_at",
                    "",
                )
            ),
        )
        for row in existing
    }

    to_add = [
        row
        for row in rows
        if (
            str(
                row.get(
                    "state_id",
                    "",
                )
            ),
            str(
                row.get(
                    "last_scan_at",
                    "",
                )
            ),
            str(
                row.get(
                    "updated_at",
                    "",
                )
            ),
        )
        not in existing_keys
    ]

    if not to_add:
        return 0

    client._call_with_rate_limit_retry(
        ("append_rows:" "source_discovery_state:" "post_acquisition"),
        lambda: ws.append_rows(
            [
                [
                    str(
                        row.get(
                            header,
                            "",
                        )
                    )
                    for header in headers
                ]
                for row in to_add
            ],
            value_input_option="USER_ENTERED",
        ),
    )

    return len(to_add)


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
            _append(
                client,
                posts_ws,
                post_headers,
                post.to_sheet_row(
                    rights_status=policy.get("rights_status", "unknown"),
                    permission_status=policy.get("permission_status", "unknown"),
                ),
                "append:source_posts:acquisition",
            )
            saved_posts += 1
            post_seen.add(post.source_post_id)
            canonical_seen.add(post.canonical_post_url)
        for item in post.media_items:
            if item.source_post_media_id in media_seen:
                continue
            policy = (policy_by_source or {}).get(post.source_id, {})
            _append(
                client,
                media_ws,
                media_headers,
                item.to_sheet_row(
                    rights_status=policy.get("rights_status", "unknown"),
                    permission_status=policy.get("permission_status", "unknown"),
                ),
                "append:source_post_media:acquisition",
            )
            saved_media += 1
            media_seen.add(item.source_post_media_id)
    return {
        "saved_source_posts": saved_posts,
        "saved_source_post_media": saved_media,
        "duplicate_source_posts": duplicates,
        "invalid_source_posts": invalid,
    }


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
        "source_id": source.get("source_id", ""),
        "source_post_id": "",
        "source_video_id": "",
        "platform": platform,
        "capability": capability,
        "provider_name": provider_name,
        "provider_version": provider_version,
        "status": status,
        "reason": str(reason)[:240],
        "retryable": str(bool(retryable)).lower(),
        "duration_ms": "",
        "attempt_count": str(max(1, attempt_count)),
        "created_at": now.isoformat(),
    }


def enrich_posts(
    source: dict[str, Any],
    posts: list[NormalizedSourcePost],
    permission: dict[str, Any],
    providers: dict[str, object],
) -> tuple[
    list[NormalizedSourcePost], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
]:
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
            provider_runs.append(
                _provider_event(source, post, f"{post.platform}.comments", comments)
            )
            if comments.ok:
                post = replace(
                    post,
                    comments=tuple(comments.data or []),
                    detail_status="COMPLETE" if comments.status == "PASS" else post.detail_status,
                )

        if post.platform in {"youtube", "tiktok"}:
            duration = next(
                (item.duration_seconds for item in post.media_items if item.duration_seconds), ""
            )
            source_video = build_source_video(
                source,
                video_url=post.canonical_post_url,
                title=(
                    post.original_post_text.splitlines()[0][:240] if post.original_post_text else ""
                ),
                duration_seconds=float(duration or 0),
                description=post.original_post_text,
                discovery_status="DISCOVERED",
            )
            source_video.update(
                {
                    "published_at": post.published_at,
                    "view_count": post.engagement.get("view_count", ""),
                    "like_count": post.engagement.get("like_count", ""),
                    "comment_count": post.engagement.get("comment_count", ""),
                    "rights_status": str(
                        permission.get("rights_status") or "approved_creator_clip"
                    ),
                    "permission_status": str(permission.get("permission_status") or "approved"),
                    "content_hash": post.content_hash,
                }
            )
            source_videos.append(source_video)
            if post.platform == "youtube" and truthy(permission.get("allow_transcription")):
                transcript = providers["youtube_transcript_api"].fetch_transcript(post)
                event = _provider_event(source, post, "youtube.transcript", transcript)
                event["source_video_id"] = source_video["source_video_id"]
                provider_runs.append(event)
                payload = transcript.data or {}
                transcripts.append(
                    normalize_transcript_row(
                        {
                            "transcript_id": f"tr_{source_video['source_video_id']}",
                            "account_id": post.target_account_id,
                            "reference_post_id": post.source_post_id,
                            "source_video_id": source_video["source_video_id"],
                            "video_id": post.external_post_id,
                            "source_id": post.source_id,
                            "source_platform": post.platform,
                            "video_url": post.canonical_post_url,
                            "transcription_provider": transcript.provider_name,
                            "transcription_status": (
                                "DONE" if transcript.status == "PASS" else transcript.status
                            ),
                            "duration_seconds": duration,
                            "transcript_text": str(payload.get("text", "")),
                            "segments_json": json.dumps(
                                payload.get("segments", []), ensure_ascii=False
                            ),
                            "language": str(payload.get("language", "")),
                            "processed_minutes": "",
                            "transcription_scope": "official_caption_only",
                            "processed_duration_seconds": duration,
                            "transcript_hash": stable_hash_text(str(payload.get("text", ""))),
                            "chunk_count": (
                                str(max(1, len(str(payload.get("text", ""))) // 1000 + 1))
                                if payload.get("text")
                                else "0"
                            ),
                            "error": "" if transcript.ok else transcript.reason,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                )
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
            _append(
                client,
                health_ws,
                health_headers,
                {
                    "backend_health_id": f"bh_{name}_{int(datetime.now().timestamp() * 1000000)}",
                    "backend_name": name,
                    "platform": result.get("platform", ""),
                    "capability": result.get("capability", ""),
                    "status": result.get("status", ""),
                    "last_success_at": now if result.get("status") == "PASS" else "",
                    "last_failure_at": now if result.get("status") != "PASS" else "",
                    "consecutive_failures": result.get("consecutive_failures", "0"),
                    "cooldown_until": result.get("cooldown_until", ""),
                    "average_duration_ms": "",
                    "failure_reason": result.get("reason", "")[:240],
                    "selected_as_primary": str(not result.get("fallback_used", False)).lower(),
                    "updated_at": now,
                },
                "append:backend_health:acquisition",
            )
        _append(
            client,
            history_ws,
            history_headers,
            {
                "routing_event_id": f"brh_{result.get('source_id', '')}_{int(datetime.now().timestamp() * 1000000)}",
                "source_id": result.get("source_id", ""),
                "platform": result.get("platform", ""),
                "capability": result.get("capability", ""),
                "primary_backend": result.get("primary_backend", ""),
                "selected_backend": result.get("selected_backend", ""),
                "fallback_used": str(result.get("fallback_used", False)).lower(),
                "shadow_backend_counts": json.dumps(
                    result.get("shadow_backend_counts", {}), sort_keys=True
                ),
                "status": result.get("status", ""),
                "reason": result.get("reason", "")[:240],
                "selected_backend_version": result.get("selected_backend_version", ""),
                "attempt_count": str(result.get("attempt_count") or 1),
                "retryable": str(
                    bool(result.get("retryable", result.get("status") != "PASS"))
                ).lower(),
                "created_at": now,
            },
            "append:backend_routing_history:acquisition",
        )


def post_matches_media_filter(
    post: NormalizedSourcePost,
    media_filter: str,
) -> bool:
    """Keep complete parent bundles; video-only never strips image children."""
    if media_filter != "video-only":
        return True

    return bool(post.media_items) and all(
        item.media_type == "video"
        for item in post.media_items
    )


def selection_with_scan_progress(
    selection: dict[str, Any],
    scan_plan: dict[str, Any],
    adapter_post_count: int,
) -> dict[str, Any]:
    """Advance the bounded cursor even when a window contains no videos."""
    start_position = int(scan_plan.get("start_position", 1))
    scanned_high_watermark = (
        start_position + max(0, int(adapter_post_count)) - 1
    )

    return {
        **selection,
        "max_scanned_position": max(
            int(selection.get("max_scanned_position", 0) or 0),
            scanned_high_watermark,
        ),
    }


def run(
    account_id: str,
    platform_filter: str,
    max_posts: int,
    *,
    apply: bool,
    shadow: bool,
    reference_only: bool = False,
    media_filter: str = "any",
    force_backfill: bool = False,
    verify_network: bool = False,
) -> dict[str, Any]:
    sources, blocked = selected_sources(
        account_id,
        platform_filter,
        reference_only=reference_only,
    )

    discovery_config = load_discovery_config()
    if reference_only and account_id == "beauty_account":
        _voice_ids, voice_policy = beauty_voice_reference_policy()
        discovery_config["max_new_videos_per_source_per_run"] = min(
            10,
            max(1, int(voice_policy.get("max_new_posts_per_source_per_run", 10))),
        )
        discovery_config["max_total_new_videos_per_run"] = min(
            30,
            max(1, int(voice_policy.get("max_total_new_posts_per_run", 30))),
        )

    if force_backfill:
        discovery_config = {
            **discovery_config,
            # General text/image inventory must not hide a shortage in the
            # video-only direct-media route. Reuse the existing bounded
            # backfill cursor instead of starting an unbounded profile crawl.
            "min_unprocessed_source_inventory_per_account": 1_000_000,
        }

    max_scan_posts = max(
        1,
        min(
            int(max_posts),
            30,
        ),
    )

    result: dict[str, Any] = {
        "status": "PLAN_ONLY",
        "account_id": account_id,
        "selected_source_count": len(sources),
        "blocked_sources": blocked,
        "network_fetch": False,
        "reference_only": reference_only,
        "media_filter": media_filter,
        "force_backfill": force_backfill,
        "would_save_source_posts": False,
        "source_results": [],
        "discovered_post_count": 0,
        "media_item_count": 0,
        "source_discovery_state_enabled": bool(
            discovery_config.get(
                "source_post_discovery_state_enabled",
                True,
            )
        ),
        "scan_limits": {
            "initial": int(
                discovery_config.get(
                    "initial_source_scan_limit",
                    30,
                )
            ),
            "incremental": int(
                discovery_config.get(
                    "incremental_source_scan_limit",
                    12,
                )
            ),
            "backfill": int(
                discovery_config.get(
                    "backfill_source_scan_limit",
                    30,
                )
            ),
            "run_hard_cap": max_scan_posts,
        },
    }

    if platform_filter in DEFERRED_REFERENCE_PLATFORMS:
        result.update(
            {
                "status": DEFERRED_REFERENCE_STATUS,
                "deferred_reason": DEFERRED_REFERENCE_REASON,
                "source_results": blocked,
            }
        )
        return result

    if not apply:
        result["source_results"] = [
            {
                "source_id": source["source_id"],
                "platform": source_platform(source),
                "capability": capability_for(source_platform(source)),
                "status": "PLAN_ONLY",
                "scan_policy": ("resolved_from_sheets_on_apply"),
            }
            for source in sources
        ]

        if not verify_network:
            return result

        router = build_router()
        result["status"] = "READ_ONLY_VERIFICATION"
        result["network_fetch"] = True
        result["source_results"] = []
        for source in sources:
            platform = source_platform(source)
            capability = capability_for(platform)
            base = {
                "source_id": str(source.get("source_id", "")),
                "platform": platform,
                "capability": capability,
                "primary_backend": router.routes[capability].primary,
            }
            try:
                routed = router.route(
                    capability,
                    source,
                    limit=max_scan_posts,
                    shadow=shadow,
                )
                normalized_posts = [post for post in routed.posts if not validate_source_post(post)]
                provenance_mismatches = [
                    post
                    for post in normalized_posts
                    if not post_matches_registered_author(post, source)
                ]
                valid_posts = [
                    post
                    for post in normalized_posts
                    if post_matches_registered_author(post, source)
                ]
                reason = ""
                if provenance_mismatches and not valid_posts:
                    reason = "registered_source_original_author_mismatch"
                elif not valid_posts:
                    reason = "no_valid_normalized_posts"
                result["source_results"].append(
                    {
                        **base,
                        "status": "PASS" if valid_posts else "BLOCKED" if provenance_mismatches else "NO_DATA",
                        "selected_backend": routed.backend_name,
                        "fallback_used": routed.fallback_used,
                        "post_count": len(valid_posts),
                        "provenance_mismatch_count": len(provenance_mismatches),
                        "reason": reason,
                    }
                )
                result["discovered_post_count"] += len(valid_posts)
                result["media_item_count"] += sum(post.media_count for post in valid_posts)
            except BackendFailure as exc:
                reason = str(exc)[:500]
                result["source_results"].append(
                    {
                        **base,
                        "status": classify_external_failure(platform, reason),
                        "reason": reason[:240],
                    }
                )
        result["status"] = (
            "PASS"
            if any(row.get("status") == "PASS" for row in result["source_results"])
            else "EXTERNAL_ACQUISITION_BLOCKED"
        )
        return result

    cfg = get_config()

    client = SheetsClient(
        cfg["sheet_id"],
        cfg["sa_dict"],
        dry_run=False,
    )

    (
        existing_post_rows,
        state_rows,
    ) = load_post_discovery_data(client)

    router = build_router()
    providers = build_provider_registry()

    posts: list[NormalizedSourcePost] = []

    selected_policy_rows: list[dict[str, Any]] = []

    state_updates: list[dict[str, Any]] = []

    source_video_rows: list[dict[str, Any]] = []

    transcript_rows: list[dict[str, Any]] = []

    provider_run_rows: list[dict[str, Any]] = []

    policy_by_source: dict[
        str,
        dict[str, str],
    ] = {}

    observability: list[dict[str, Any]] = []

    for source in sources:
        platform = source_platform(source)
        capability = capability_for(platform)

        source_id = str(source["source_id"])

        source_account_id = account_for(source)

        scan_plan = plan_source_scan(
            source_id=source_id,
            account_id=source_account_id,
            item_type="post",
            existing_rows=(existing_post_rows),
            state_rows=state_rows,
            config=discovery_config,
        )

        scan_plan = {
            **scan_plan,
            "scan_limit": min(
                int(scan_plan["scan_limit"]),
                max_scan_posts,
            ),
        }

        base = {
            "source_id": source_id,
            "platform": platform,
            "capability": capability,
            "primary_backend": (router.routes[capability].primary),
            "scan_mode": scan_plan["mode"],
            "start_position": (scan_plan["start_position"]),
            "scan_limit": scan_plan["scan_limit"],
            "inventory_count": (scan_plan["inventory_count"]),
            "inventory_target": (scan_plan["inventory_target"]),
        }

        permission = (
            reference_only_permission(source)
            if reference_only
            else ledger_permission(
                client,
                source_id,
                account_id=source_account_id,
                source_handle=str(source.get("source_handle") or source.get("author_handle") or ""),
            )
        )

        if not permission:
            item = {
                **base,
                "status": "BLOCKED",
                "reason": ("active_permission_ledger_missing"),
            }

            result["source_results"].append(item)

            observability.append(item)
            continue

        if len(selected_policy_rows) >= int(scan_plan["max_total_new"]):
            item = {
                **base,
                "status": "SKIPPED",
                "reason": ("max_total_new_reached"),
                "post_count": 0,
                "adapter_post_count": 0,
                "duplicate_post_count": 0,
                "stop_reason": ("max_total_new_reached"),
            }

            result["source_results"].append(item)

            observability.append(item)
            continue

        route_source = {
            **source,
            "_discovery_start_position": (scan_plan["start_position"]),
            "_discovery_mode": (scan_plan["mode"]),
        }

        try:
            routed = router.route(
                capability,
                route_source,
                limit=int(scan_plan["scan_limit"]),
                shadow=shadow,
            )

            selected_adapter = router.adapters.get(routed.backend_name)

            provider_run_rows.append(
                _route_provider_event(
                    source,
                    platform=platform,
                    capability=capability,
                    provider_name=(routed.backend_name),
                    provider_version=str(
                        getattr(
                            selected_adapter,
                            "backend_version",
                            "unknown",
                        )
                    ),
                    status="PASS",
                    attempt_count=len(routed.attempted_backends),
                )
            )

            normalized_posts = [post for post in routed.posts if not validate_source_post(post)]
            provenance_mismatches = [
                post
                for post in normalized_posts
                if not post_matches_registered_author(post, source)
            ]
            valid_before_policy = [
                post
                for post in normalized_posts
                if post_matches_registered_author(post, source)
            ]
            adapter_post_count = len(valid_before_policy)

            if media_filter == "video-only":
                valid_before_policy = [
                    post
                    for post in valid_before_policy
                    if post_matches_media_filter(
                        post,
                        media_filter,
                    )
                ]

            candidates = [
                source_post_candidate(
                    post,
                    source_position=(int(scan_plan["start_position"]) + offset),
                )
                for offset, post in enumerate(valid_before_policy)
            ]

            selection = select_unique_candidates(
                candidates=candidates,
                existing_rows=(existing_post_rows),
                selected_this_run=(selected_policy_rows),
                duplicate_checker=(is_duplicate_source_post),
                scan_plan=scan_plan,
            )

            selected_rows = list(
                selection.get(
                    "selected",
                    [],
                )
            )

            selected_policy_rows.extend(selected_rows)

            selected_posts = [row["_post"] for row in selected_rows]

            (
                valid,
                videos,
                transcripts,
                provider_events,
            ) = enrich_posts(
                source,
                selected_posts,
                permission,
                providers,
            )

            valid = [post for post in valid if not validate_source_post(post)]

            posts.extend(valid)

            source_video_rows.extend(videos)

            transcript_rows.extend(transcripts)

            provider_run_rows.extend(provider_events)

            policy_by_source[source_id] = {
                "rights_status": str(permission.get("rights_status") or "reference_only"),
                "permission_status": str(permission.get("permission_status") or "reference_only"),
            }

            latest_candidate = candidates[0] if candidates else {}

            state_selection = {
                **selection_with_scan_progress(
                    selection,
                    scan_plan,
                    adapter_post_count,
                ),
                "new_count": len(valid),
            }

            state_update = build_state_update(
                scan_plan=scan_plan,
                selection=(state_selection),
                latest_seen_item_id=str(
                    latest_candidate.get(
                        "external_post_id",
                        "",
                    )
                ),
                latest_seen_published_at=str(
                    latest_candidate.get(
                        "published_at",
                        "",
                    )
                ),
                platform=platform,
            )

            state_updates.append(state_update)

            item = {
                **base,
                "status": (
                    "PASS"
                    if valid
                    else "BLOCKED"
                    if provenance_mismatches
                    else "NO_DATA"
                ),
                "reason": (
                    ""
                    if valid
                    else "registered_source_original_author_mismatch"
                    if provenance_mismatches
                    else "no_eligible_new_source_post"
                ),
                "selected_backend": (routed.backend_name),
                "selected_backend_version": str(
                    getattr(
                        selected_adapter,
                        "backend_version",
                        "unknown",
                    )
                ),
                "attempt_count": len(routed.attempted_backends),
                "retryable": False,
                "fallback_used": (routed.fallback_used),
                "adapter_post_count": adapter_post_count,
                "provenance_mismatch_count": len(provenance_mismatches),
                "media_filtered_post_count": len(valid_before_policy),
                "post_count": len(valid),
                "duplicate_post_count": int(
                    selection.get(
                        "duplicate_count",
                        0,
                    )
                ),
                "max_duplicate_streak": int(
                    selection.get(
                        "max_duplicate_streak",
                        0,
                    )
                ),
                "scanned_post_count": int(
                    selection.get(
                        "scanned_count",
                        0,
                    )
                ),
                "stop_reason": str(
                    selection.get(
                        "stop_reason",
                        "",
                    )
                ),
                "state_update_planned": True,
                "shadow_backend_counts": (routed.shadow_results),
            }

        except BackendFailure as exc:
            primary_adapter = router.adapters.get(base["primary_backend"])

            attempts = 1 + len(router.routes[capability].fallbacks)

            provider_run_rows.append(
                _route_provider_event(
                    source,
                    platform=platform,
                    capability=capability,
                    provider_name=base["primary_backend"],
                    provider_version=str(
                        getattr(
                            primary_adapter,
                            "backend_version",
                            "unknown",
                        )
                    ),
                    status="FAILED",
                    reason=str(exc),
                    retryable=True,
                    attempt_count=attempts,
                )
            )

            item = {
                **base,
                "status": "FAILED",
                "reason": str(exc)[:240],
                "attempt_count": attempts,
                "retryable": True,
                "post_count": 0,
                "adapter_post_count": 0,
                "duplicate_post_count": 0,
                "state_update_planned": False,
            }

        result["source_results"].append(item)

        observability.append(item)

    persisted = persist(
        client,
        posts,
        policy_by_source,
    )

    persisted["saved_source_videos"] = persist_auxiliary(
        client,
        "source_videos",
        source_video_rows,
        identity_fields=("source_video_id",),
    )

    persisted["saved_video_transcripts"] = persist_auxiliary(
        client,
        "video_transcripts",
        transcript_rows,
        identity_fields=("transcript_id",),
    )

    persisted["saved_provider_runs"] = persist_auxiliary(
        client,
        "provider_runs",
        provider_run_rows,
        identity_fields=("provider_run_id",),
    )

    if discovery_config.get(
        "source_post_discovery_state_enabled",
        True,
    ):
        persisted["saved_source_discovery_state"] = append_discovery_state_to_sheets(
            client,
            state_updates,
        )
    else:
        persisted["saved_source_discovery_state"] = 0

    persist_observability(
        client,
        observability,
    )

    result.update(persisted)

    result.update(
        {
            "status": "APPLIED",
            "network_fetch": True,
            "discovered_post_count": (len(posts)),
            "media_item_count": sum(post.media_count for post in posts),
            "discovery_state_update_count": (len(state_updates)),
            "would_save_source_posts": (bool(posts)),
        }
    )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=("acquire owner-approved source posts " "via primary/fallback adapters")
    )

    parser.add_argument(
        "--account-id",
        default="all",
        choices=[
            "all",
            "night_scout",
            "liver_manager",
            "beauty_account",
        ],
    )

    parser.add_argument(
        "--platform",
        default="all",
        choices=[
            "all",
            "threads",
            "youtube",
            "tiktok",
            "x",
        ],
    )

    parser.add_argument(
        "--max-posts",
        type=int,
        default=30,
        help=("hard cap for each bounded source scan; " "policy normally uses 30/12/30"),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--confirm-acquisition",
        action="store_true",
    )

    parser.add_argument(
        "--shadow",
        action="store_true",
        help=("run configured analysis-only " "shadow adapters when installed"),
    )
    parser.add_argument(
        "--reference-only",
        action="store_true",
        help="fetch enabled reference sources without granting media reuse",
    )
    parser.add_argument(
        "--media-filter",
        choices=["any", "video-only"],
        default="any",
        help="persist all posts or only complete video-only parent posts",
    )
    parser.add_argument(
        "--force-backfill",
        action="store_true",
        help="use the bounded historical cursor even when general inventory is full",
    )
    parser.add_argument(
        "--verify-network",
        action="store_true",
        help="bounded public read-only fetch; never connects to or writes Sheets",
    )

    args = parser.parse_args()

    if args.apply and not args.confirm_acquisition:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": ("--apply requires " "--confirm-acquisition"),
                }
            )
        )

        return 1

    if args.dry_run and args.apply:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": ("choose --dry-run or --apply"),
                }
            )
        )

        return 1

    if args.verify_network and args.apply:
        print(json.dumps({"status": "BLOCKED", "reason": "--verify-network cannot be combined with --apply"}))
        return 1

    if args.verify_network and not args.reference_only:
        print(json.dumps({"status": "BLOCKED", "reason": "--verify-network requires --reference-only"}))
        return 1

    outcome = run(
        args.account_id,
        args.platform,
        args.max_posts,
        apply=args.apply,
        shadow=args.shadow,
        reference_only=args.reference_only,
        media_filter=args.media_filter,
        force_backfill=args.force_backfill,
        verify_network=args.verify_network,
    )

    print(
        json.dumps(
            outcome,
            ensure_ascii=False,
            indent=2,
        )
    )

    return (
        0
        if outcome["status"]
        in {
            "PLAN_ONLY",
            "APPLIED",
            "PASS",
            "UNVERIFIED_EXTERNAL",
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
