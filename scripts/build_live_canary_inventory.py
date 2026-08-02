#!/usr/bin/env python3
"""Build a read-only ten-slot route canary inventory from live Sheets evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
    canonical_activation_type,
)
from build_bounded_media_canary_plan import build_plan
from final_production_contracts import (
    APPROVED_RIGHTS,
    is_active_permission,
)


def _rows(use_sheets: bool) -> tuple[dict[str, list[dict[str, Any]]], str]:
    empty = {key: [] for key in ("queue", "source_posts", "source_post_media", "media_permissions", "source_videos", "video_clip_candidates", "media_assets")}
    if not use_sheets:
        return empty, "use_sheets_required"
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        return {key: [dict(row) for row in client._ws(key).get_all_records()] for key in empty}, "READ_OK"
    except Exception as exc:
        return empty, type(exc).__name__


def _public_text(row: dict[str, Any]) -> str:
    return str(row.get("public_post_text") or row.get("text") or "").strip()


def _fresh(row: dict[str, Any]) -> bool:
    return (
        str(row.get("canary_id", "")).startswith("canary_fresh_")
        and str(row.get("status", "")).upper() not in {"INVALID_CONTENT_CANARY", "LEGACY_INVALID_CANARY", "QUARANTINED", "SUPERSEDED_QUALITY"}
        and str(row.get("excluded_from_activation", "")).strip().lower() not in {"1", "true", "yes"}
        and str(row.get("repost_prohibited", "")).strip().lower() not in {"1", "true", "yes"}
    )


def _queue_content_type(row: dict[str, Any]) -> str:
    """Prefer the canonical content type; retain only the legacy fallback."""
    return str(row.get("content_type") or row.get("media_type") or "").strip().lower()


def _quality_fields(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "batch_id", "batch_diversity_status", "batch_similarity_score",
        "hook_similarity_score", "closing_similarity_score", "structure_variant", "structure_similarity_score",
        "shared_sentence_count", "shared_sentences", "shared_closing_detected",
        "shared_hook_detected", "compared_candidate_ids",
        "structure_compared_candidate_ids", "diversity_blocked_reasons",
        "primary_topic", "supporting_topics", "topic_confidence",
        "primary_topic_evidence_score", "primary_topic_direct_confidence", "topic_coherence_status",
        "topic_coherence_score", "off_topic_sentence_count", "off_topic_sentences",
        "hook_topic", "closing_topic", "visual_topic",
        "hook_topic_match", "closing_topic_match", "visual_topic_match",
        "topic_blocked_reasons", "quality_gate_version",
        "generation_attempt", "generation_rule_version",
        "feature_schema_version", "hook_text", "body_text", "closing_text",
        "cta_intent", "key_claims_json", "post_design_json", "visual_plan_json",
        "media_primary_topic", "visual_cta_match", "visual_plan_version",
        "visual_plan_attempt", "visual_text_hash", "claim_support_json", "alignment_blocked_reasons",
    )
    return {key: row.get(key, "") for key in keys}




def _canonical_queue_kind(
    row: dict[str, Any],
) -> str:
    return canonical_activation_type(
        row.get("content_type")
        or row.get("generation_mode")
        or row.get("media_type")
        or "",
        content_route=row.get(
            "content_route",
            "",
        ),
    )



def _latest_complete_first_wave_batch(
    queue: list[dict[str, Any]],
) -> str:
    required = {
        (
            account,
            kind,
        )
        for account in ACCOUNTS
        for kind in (
            "original_text",
            "direct_reference_media",
        )
    }

    grouped: dict[
        str,
        set[tuple[str, str]],
    ] = {}

    newest: dict[str, str] = {}

    for row in queue:
        if not _fresh(row):
            continue

        batch = str(
            row.get(
                "batch_id",
                "",
            )
        ).strip()

        account = str(
            row.get(
                "account_id",
                "",
            )
        ).strip()

        kind = _canonical_queue_kind(
            row
        )

        if (
            not batch
            or (
                account,
                kind,
            )
            not in required
        ):
            continue

        grouped.setdefault(
            batch,
            set(),
        ).add(
            (
                account,
                kind,
            )
        )

        newest[batch] = max(
            newest.get(
                batch,
                "",
            ),
            str(
                row.get(
                    "created_at",
                    "",
                )
            ),
        )

    complete = [
        batch
        for batch, keys in grouped.items()
        if keys == required
    ]

    return max(
        complete,
        key=lambda batch: (
            newest.get(
                batch,
                "",
            ),
            batch,
        ),
        default="",
    )


def _permission(permissions: list[dict[str, Any]], source_id: str, account_id: str, operation: str) -> dict[str, Any] | None:
    return next((item for item in permissions if str(item.get("source_id", "")) == source_id and is_active_permission(item, account_id=account_id, operation=operation)), None)


def build_inventory(
    datasets: dict[
        str,
        list[dict[str, Any]],
    ],
    *,
    wave: str = "all_10",
    batch_id: str = "",
) -> dict[str, Any]:
    if wave == "all_12":
        wave = "all_10"

    if wave not in {
        "all_10",
        "first_wave",
    }:
        raise ValueError(
            "unsupported_wave"
        )

    def json_list(
        value: Any,
    ) -> list[str]:
        if isinstance(value, list):
            return [
                str(item).strip()
                for item in value
                if str(item).strip()
            ]

        try:
            parsed = json.loads(
                str(value or "[]")
            )
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            return []

        if not isinstance(
            parsed,
            list,
        ):
            return []

        return [
            str(item).strip()
            for item in parsed
            if str(item).strip()
        ]

    candidates: list[
        dict[str, Any]
    ] = []

    queue = datasets.get(
        "queue",
        [],
    )

    posts = datasets.get(
        "source_posts",
        [],
    )

    media = datasets.get(
        "source_post_media",
        [],
    )

    permissions = datasets.get(
        "media_permissions",
        [],
    )

    clips = datasets.get(
        "video_clip_candidates",
        [],
    )

    assets = datasets.get(
        "media_assets",
        [],
    )

    source_videos = {
        str(
            row.get(
                "source_video_id",
                "",
            )
        ): row
        for row in datasets.get(
            "source_videos",
            [],
        )
    }

    selected_batch_id = (
        batch_id
        or (
            _latest_complete_first_wave_batch(
                queue
            )
            if wave == "first_wave"
            else ""
        )
    )

    for account_id in ACCOUNTS:
        account_queue = sorted(
            (
                row
                for row in queue
                if str(
                    row.get(
                        "account_id",
                        "",
                    )
                )
                == account_id
                and _fresh(row)
                and (
                    not selected_batch_id
                    or str(
                        row.get(
                            "batch_id",
                            "",
                        )
                    )
                    == selected_batch_id
                )
            ),
            key=lambda row: str(
                row.get(
                    "created_at",
                    "",
                )
            ),
            reverse=True,
        )

        text_types = (
            (
                "original_text",
            )
            if wave == "first_wave"
            else (
                "original_text",
                "reference_text",
                "pdca_text",
            )
        )

        for kind in text_types:
            selected = next(
                (
                    row
                    for row in account_queue
                    if (
                        _canonical_queue_kind(
                            row
                        )
                        == kind
                        and _public_text(
                            row
                        )
                    )
                ),
                None,
            )

            if not selected:
                continue

            candidates.append(
                {
                    "account_id": (
                        account_id
                    ),
                    "canary_type": kind,
                    "content_route": kind,
                    "canary_id": (
                        selected.get(
                            "canary_id",
                            "",
                        )
                    ),
                    "public_post_text": (
                        _public_text(
                            selected
                        )
                    ),
                    (
                        "persona_"
                        "validator_status"
                    ): selected.get(
                        "account_fit_status",
                        "PASS",
                    ),
                    (
                        "final_public_post_"
                        "validator_status"
                    ): selected.get(
                        "validator_status",
                        "PASS",
                    ),
                    (
                        "internal_leak_"
                        "status"
                    ): selected.get(
                        "internal_leak_status",
                        "",
                    ),
                    "queue_id": (
                        selected.get(
                            "queue_id",
                            "",
                        )
                    ),
                    "content_hash": (
                        selected.get(
                            "content_hash",
                            "",
                        )
                    ),
                    (
                        "recent_post_"
                        "similarity"
                    ): selected.get(
                        (
                            "recent_post_"
                            "similarity"
                        ),
                        "",
                    ),
                    **_quality_fields(
                        selected
                    ),
                }
            )

        account_posts = {
            str(
                row.get(
                    "source_post_id",
                    "",
                )
            ): row
            for row in posts
            if str(
                row.get(
                    "target_account_id"
                )
                or row.get(
                    "account_id"
                )
                or ""
            )
            == account_id
        }

        media_by_parent: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        for item in media:
            media_by_parent.setdefault(
                str(
                    item.get(
                        "source_post_id",
                        "",
                    )
                ),
                [],
            ).append(item)

        assets_by_id = {
            str(
                row.get("media_id")
                or row.get(
                    "media_asset_id"
                )
                or ""
            ): row
            for row in assets
        }

        direct_options: list[
            tuple[
                tuple[int, int, str],
                dict[str, Any],
            ]
        ] = []

        for matching_queue in (
            row
            for row in account_queue
            if (
                _canonical_queue_kind(
                    row
                )
                == "direct_reference_media"
            )
        ):
            parent_id = str(
                matching_queue.get(
                    "source_post_id",
                    "",
                )
            )

            parent = account_posts.get(
                parent_id
            )

            if not parent:
                continue

            source_id = str(
                parent.get(
                    "source_id",
                    "",
                )
            )

            permission = _permission(
                permissions,
                source_id,
                account_id,
                "direct",
            )

            if not permission:
                continue

            bundle = sorted(
                media_by_parent.get(
                    parent_id,
                    [],
                ),
                key=lambda item: int(
                    item.get(
                        "media_index",
                        0,
                    )
                    or 0
                ),
            )

            asset_ids = json_list(
                matching_queue.get(
                    "media_asset_ids_json"
                )
            )

            single_asset_id = str(
                matching_queue.get(
                    "media_asset_id",
                    "",
                )
            )

            if (
                not asset_ids
                and single_asset_id
            ):
                asset_ids = [
                    single_asset_id
                ]

            if not asset_ids:
                asset_ids = [
                    str(
                        item.get(
                            "media_asset_id"
                        )
                        or item.get(
                            (
                                "source_post_"
                                "media_id"
                            ),
                            "",
                        )
                    )
                    for item in bundle
                    if str(
                        item.get(
                            "media_asset_id"
                        )
                        or item.get(
                            (
                                "source_post_"
                                "media_id"
                            ),
                            "",
                        )
                    )
                ]

            urls = json_list(
                matching_queue.get(
                    "media_urls_json"
                )
            )

            single_url = str(
                matching_queue.get(
                    "media_url",
                    "",
                )
            ).strip()

            if not urls and single_url:
                urls = [
                    single_url
                ]

            if not urls:
                urls = [
                    str(
                        item.get(
                            "storage_url"
                        )
                        or assets_by_id.get(
                            str(
                                item.get(
                                    "media_asset_id",
                                    "",
                                )
                            ),
                            {},
                        ).get(
                            "storage_url",
                            "",
                        )
                    ).strip()
                    for item in bundle
                    if str(
                        item.get(
                            "storage_url"
                        )
                        or assets_by_id.get(
                            str(
                                item.get(
                                    "media_asset_id",
                                    "",
                                )
                            ),
                            {},
                        ).get(
                            "storage_url",
                            "",
                        )
                    ).strip()
                ]

            if not urls:
                continue

            runtime_type = (
                _queue_content_type(
                    matching_queue
                )
            )

            first_asset = (
                assets_by_id.get(
                    asset_ids[0],
                    {},
                )
                if asset_ids
                else {}
            )

            publisher_type = str(
                matching_queue.get(
                    "publisher_media_type",
                    "",
                )
            ).upper()

            if not publisher_type:
                if len(urls) > 1:
                    publisher_type = (
                        "CAROUSEL"
                    )
                elif (
                    runtime_type
                    == "direct_video"
                    or str(
                        first_asset.get(
                            "media_type",
                            "",
                        )
                    ).lower()
                    == "video"
                ):
                    publisher_type = (
                        "VIDEO"
                    )
                else:
                    publisher_type = (
                        "IMAGE"
                    )

            candidate = {
                "account_id": (
                    account_id
                ),
                "canary_type": (
                    "direct_reference_media"
                ),
                "content_route": (
                    "direct_reference_media"
                ),
                "runtime_content_type": (
                    runtime_type
                ),
                "canary_id": (
                    matching_queue.get(
                        "canary_id",
                        "",
                    )
                ),
                "queue_id": (
                    matching_queue.get(
                        "queue_id",
                        "",
                    )
                ),
                "source_id": source_id,
                "rights_status": (
                    permission.get(
                        "rights_status",
                        "",
                    )
                ),
                "permission_status": (
                    permission.get(
                        "permission_status",
                        "",
                    )
                ),
                "permission_evidence": (
                    permission.get(
                        "evidence_reference",
                        "",
                    )
                ),
                "public_post_text": (
                    _public_text(
                        matching_queue
                    )
                ),
                (
                    "persona_"
                    "validator_status"
                ): matching_queue.get(
                    "account_fit_status",
                    "",
                ),
                (
                    "final_public_post_"
                    "validator_status"
                ): matching_queue.get(
                    "validator_status",
                    "",
                ),
                (
                    "internal_leak_"
                    "status"
                ): matching_queue.get(
                    "internal_leak_status",
                    "",
                ),
                "publisher_media_type": (
                    publisher_type
                ),
                "source_post_id": (
                    parent_id
                ),
                "media_asset_id": (
                    asset_ids[0]
                    if asset_ids
                    else ""
                ),
                "media_url": (
                    urls[0]
                ),
                "media_asset_ids": (
                    asset_ids
                    if len(asset_ids) > 1
                    else []
                ),
                "media_urls": (
                    urls
                    if len(urls) > 1
                    else []
                ),
                "content_hash": (
                    matching_queue.get(
                        "content_hash",
                        "",
                    )
                ),
                (
                    "recent_post_"
                    "similarity"
                ): matching_queue.get(
                    (
                        "recent_post_"
                        "similarity"
                    ),
                    "",
                ),
                "alignment_status": (
                    matching_queue.get(
                        "alignment_status",
                        "",
                    )
                ),
                (
                    "final_alignment_"
                    "score"
                ): matching_queue.get(
                    (
                        "final_alignment_"
                        "score"
                    ),
                    "",
                ),
                (
                    "main_claim_"
                    "coverage"
                ): matching_queue.get(
                    (
                        "main_claim_"
                        "coverage"
                    ),
                    "",
                ),
                (
                    "unsupported_claim_"
                    "count"
                ): matching_queue.get(
                    (
                        "unsupported_claim_"
                        "count"
                    ),
                    "",
                ),
                (
                    "source_copy_"
                    "similarity"
                ): matching_queue.get(
                    (
                        "source_copy_"
                        "similarity"
                    ),
                    "",
                ),
                "duration_seconds": (
                    matching_queue.get(
                        "duration_seconds"
                    )
                    or first_asset.get(
                        "duration_seconds"
                    )
                    or first_asset.get(
                        "duration",
                        "",
                    )
                ),
                "aspect_ratio": (
                    matching_queue.get(
                        "aspect_ratio"
                    )
                    or first_asset.get(
                        "aspect_ratio",
                        "",
                    )
                ),
                **_quality_fields(
                    matching_queue
                ),
            }

            quality_keys = (
                "alignment_status",
                "feature_schema_version",
                "visual_plan_version",
                "batch_id",
                "batch_diversity_status",
                "topic_coherence_status",
                "quality_gate_version",
            )

            quality_score = sum(
                bool(
                    str(
                        candidate.get(
                            key,
                            "",
                        )
                    ).strip()
                )
                for key in quality_keys
            )

            media_priority = {
                "VIDEO": 3,
                "CAROUSEL": 2,
                "IMAGE": 1,
            }.get(
                publisher_type,
                0,
            )

            direct_options.append(
                (
                    (
                        quality_score,
                        media_priority,
                        str(
                            matching_queue.get(
                                "created_at",
                                "",
                            )
                        ),
                    ),
                    candidate,
                )
            )

        if direct_options:
            candidates.append(
                max(
                    direct_options,
                    key=lambda item: item[0],
                )[1]
            )

        if wave == "first_wave":
            continue

        account_clips = sorted(
            (
                clip
                for clip in clips
                if str(
                    clip.get(
                        "account_id",
                        "",
                    )
                )
                == account_id
            ),
            key=lambda clip: (
                str(
                    clip.get(
                        "created_at",
                        "",
                    )
                ),
                str(
                    clip.get(
                        "clip_candidate_id"
                    )
                    or clip.get(
                        "clip_id"
                    )
                    or ""
                ),
            ),
            reverse=True,
        )

        for clip in account_clips:
            if str(
                clip.get(
                    "rights_status",
                    "",
                )
            ).lower() not in APPROVED_RIGHTS:
                continue

            source_video = (
                source_videos.get(
                    str(
                        clip.get(
                            "source_video_id",
                            "",
                        )
                    ),
                    {},
                )
            )

            source_id = str(
                clip.get(
                    "source_id"
                )
                or source_video.get(
                    "source_id"
                )
                or ""
            )

            if not source_id:
                continue

            permission = _permission(
                permissions,
                source_id,
                account_id,
                "clip",
            )

            asset = next(
                (
                    item
                    for item in assets
                    if str(
                        item.get(
                            (
                                "clip_candidate_"
                                "id"
                            )
                        )
                        or item.get(
                            "video_clip_id"
                        )
                        or ""
                    )
                    == str(
                        clip.get(
                            (
                                "clip_candidate_"
                                "id"
                            ),
                            "",
                        )
                    )
                ),
                {},
            )

            if (
                not permission
                or not str(
                    asset.get(
                        "storage_url",
                        "",
                    )
                )
            ):
                continue

            matching_queue = next(
                (
                    row
                    for row in account_queue
                    if str(
                        row.get(
                            (
                                "clip_candidate_"
                                "id"
                            ),
                            "",
                        )
                    )
                    == str(
                        clip.get(
                            (
                                "clip_candidate_"
                                "id"
                            ),
                            "",
                        )
                    )
                    and (
                        _canonical_queue_kind(
                            row
                        )
                        == (
                            "approved_"
                            "source_clip"
                        )
                    )
                ),
                {},
            )

            if not matching_queue:
                continue

            candidates.append(
                {
                    "account_id": (
                        account_id
                    ),
                    "canary_type": (
                        "approved_source_clip"
                    ),
                    "content_route": (
                        "approved_source_clip"
                    ),
                    "canary_id": (
                        matching_queue.get(
                            "canary_id",
                            "",
                        )
                    ),
                    "queue_id": (
                        matching_queue.get(
                            "queue_id",
                            "",
                        )
                    ),
                    "source_id": source_id,
                    "rights_status": (
                        permission.get(
                            "rights_status",
                            "",
                        )
                    ),
                    "permission_status": (
                        permission.get(
                            (
                                "permission_"
                                "status"
                            ),
                            "",
                        )
                    ),
                    "permission_evidence": (
                        permission.get(
                            (
                                "evidence_"
                                "reference"
                            ),
                            "",
                        )
                    ),
                    "public_post_text": (
                        _public_text(
                            matching_queue
                        )
                    ),
                    (
                        "persona_"
                        "validator_status"
                    ): matching_queue.get(
                        (
                            "account_fit_"
                            "status"
                        ),
                        "",
                    ),
                    (
                        "final_public_post_"
                        "validator_status"
                    ): matching_queue.get(
                        "validator_status",
                        "",
                    ),
                    (
                        "internal_leak_"
                        "status"
                    ): matching_queue.get(
                        (
                            "internal_leak_"
                            "status"
                        ),
                        "",
                    ),
                    (
                        "publisher_media_"
                        "type"
                    ): matching_queue.get(
                        (
                            "publisher_media_"
                            "type"
                        ),
                        "",
                    ),
                    "source_video_id": (
                        clip.get(
                            "source_video_id",
                            "",
                        )
                    ),
                    "clip_candidate_id": (
                        clip.get(
                            (
                                "clip_candidate_"
                                "id"
                            ),
                            "",
                        )
                    ),
                    "local_path": (
                        asset.get(
                            "local_path",
                            "ready",
                        )
                    ),
                    "start_seconds": (
                        clip.get(
                            "start_seconds",
                            "",
                        )
                    ),
                    "end_seconds": (
                        clip.get(
                            "end_seconds",
                            "",
                        )
                    ),
                    "content_hash": (
                        matching_queue.get(
                            "content_hash",
                            "",
                        )
                    ),
                    (
                        "recent_post_"
                        "similarity"
                    ): matching_queue.get(
                        (
                            "recent_post_"
                            "similarity"
                        ),
                        "",
                    ),
                    "alignment_status": (
                        matching_queue.get(
                            (
                                "alignment_"
                                "status"
                            ),
                            "",
                        )
                    ),
                    (
                        "final_alignment_"
                        "score"
                    ): matching_queue.get(
                        (
                            "final_alignment_"
                            "score"
                        ),
                        "",
                    ),
                    (
                        "main_claim_"
                        "coverage"
                    ): matching_queue.get(
                        (
                            "main_claim_"
                            "coverage"
                        ),
                        "",
                    ),
                    (
                        "unsupported_claim_"
                        "count"
                    ): matching_queue.get(
                        (
                            "unsupported_claim_"
                            "count"
                        ),
                        "",
                    ),
                    (
                        "source_copy_"
                        "similarity"
                    ): matching_queue.get(
                        (
                            "source_copy_"
                            "similarity"
                        ),
                        "",
                    ),
                    "media_asset_id": (
                        asset.get(
                            "media_id"
                        )
                        or asset.get(
                            "media_asset_id",
                            "",
                        )
                    ),
                    "media_url": (
                        asset.get(
                            "storage_url",
                            "",
                        )
                    ),
                    "duration_seconds": (
                        matching_queue.get(
                            "duration_seconds"
                        )
                        or clip.get(
                            "duration_seconds"
                        )
                        or asset.get(
                            "duration_seconds"
                        )
                        or asset.get(
                            "duration",
                            "",
                        )
                    ),
                    "aspect_ratio": (
                        matching_queue.get(
                            "aspect_ratio"
                        )
                        or clip.get(
                            "aspect_ratio"
                        )
                        or asset.get(
                            "aspect_ratio",
                            "",
                        )
                    ),
                    **_quality_fields(
                        matching_queue
                    ),
                }
            )

            break

    plan = build_plan(
        candidates,
        wave=wave,
    )

    return {
        **plan,
        "status": "LIVE_INVENTORY_PLAN",
        "selected_batch_id": (
            selected_batch_id
        ),
        "candidate_count": len(
            candidates
        ),
        "candidates": candidates,
        "would_write": False,
        "would_post": False,
    }



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--wave", choices=["all_10", "all_12", "first_wave"], default="all_10")
    parser.add_argument("--batch-id", default="")
    args = parser.parse_args(); data, source = _rows(args.use_sheets); result = build_inventory(data, wave=args.wave, batch_id=args.batch_id); result["sheets_status"] = source
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); result["output_path"] = str(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
