"""Phase 5B-6A: fail-closed, publisher-level media interlock.

No authenticated publication authority exists yet. A Sheets 'APPROVED',
signed-in reviewer, ready flag, environment switch or local SQLite review
record is NOT an atomic, publish-time authorization. Keep real media network
requests impossible until a future integrated authority is deployed, audited
and tested in *every* publishing entrypoint.

This module is intentionally not configurable through environment variables
or caller-supplied booleans. Do not add a bypass to publisher kwargs.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROTECTED_MEDIA_SLOTS = frozenset({
    ("night_scout", "ns_1800_direct_media"),
    ("night_scout", "ns_2100_clip_media"),
    ("liver_manager", "lm_1600_direct_media"),
    ("liver_manager", "lm_1800_clip_media"),
})
MEDIA_TYPES = frozenset({"IMAGE", "VIDEO", "CAROUSEL"})
MEDIA_ROUTES = frozenset({
    "direct_reference_media", "direct_image", "direct_video",
    "direct_carousel", "approved_source_clip", "generated_clip",
    "hybrid_media", "video_clip", "saved_direct_reference_media",
    "saved_approved_source_clip",
})
MEDIA_KEYS = (
    "media_asset_id", "media_url", "media_urls", "video_clip_id",
    "clip_candidate_id", "media_asset_ids_json", "media_urls_json",
)


def _field(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    return str(value).strip() if isinstance(value, (str, int, float, bool)) else ""


def media_publish_authority_required(
    *,
    account: Mapping[str, Any] | None,
    queue_item: Mapping[str, Any] | None,
    derivative: Mapping[str, Any] | None,
    has_media: bool = False,
) -> bool:
    """Detect attached media or a protected media route, even with omitted flags.

    A caller cannot turn an *actual* media upload into a text-only publish
    by setting media_required=false, missing the slot, or spoofing approval.
    When metadata is missing AND no media is attached, the request is text
    only; Phase 5B-6B must enforce canonical queue binding for all paths.
    """
    if has_media:
        return True
    if not isinstance(account, Mapping) or not isinstance(queue_item, Mapping):
        # Missing row context is not proof that the media is safe.
        return True
    account_id = _field(account, "account_id")
    if account_id != _field(queue_item, "account_id") and _field(queue_item, "account_id"):
        return True
    for row in (queue_item, derivative or {}):
        if not isinstance(row, Mapping):
            return True
        if _field(row, "media_required").lower() in {"1", "true", "yes"}:
            return True
        if (_field(row, "media_type").upper() in MEDIA_TYPES
                or _field(row, "publisher_media_type").upper() in MEDIA_TYPES):
            return True
        if any(
            value and value not in {"[]", "null", "None"}
            for key in MEDIA_KEYS
            for value in (_field(row, key),)
        ):
            return True
        # Some runtime paths retain a Python list rather than serialized JSON.
        if any(isinstance(row.get(key), (tuple, list)) and bool(row[key])
               for key in ("media_urls", "media_urls_json", "media_asset_ids_json")):
            return True
        if any(_field(row, key).lower() in MEDIA_ROUTES
               for key in ("generation_mode", "content_type", "content_route")):
            return True
        if (account_id, _field(row, "slot_id")) in PROTECTED_MEDIA_SLOTS:
            return True
    return False


def media_publish_interlock_reason(
    *, account: Mapping[str, Any] | None,
    queue_item: Mapping[str, Any] | None,
    derivative: Mapping[str, Any] | None,
    has_media: bool = False,
) -> str | None:
    """Return a static public reason; never serialize sensitive queue fields."""
    if media_publish_authority_required(
        account=account, queue_item=queue_item,
        derivative=derivative, has_media=has_media,
    ):
        return "MEDIA_AUTHORITY_NOT_CONNECTED"
    return None

def block_legacy_ready_transition(
    current: Mapping[str, Any] | None,
    changes: Mapping[str, Any],
) -> bool:
    """Fail closed on protected-media READY updates and inserted READY rows.

    Inspect BOTH the old row and the proposed row: a patch clearing a media
    marker cannot smuggle a media row through. This is a local transition
    check, not an atomic Google Sheets CAS or a publication authorization.
    """
    if str(changes.get("status") or "").strip().upper() != "READY":
        return False
    if not isinstance(current, Mapping) or not isinstance(changes, Mapping):
        return True
    for row in (current, {**current, **changes}):
        account_id = _field(row, "account_id")
        if not account_id or not _field(row, "platform"):
            return True
        if media_publish_authority_required(
            account={"account_id": account_id},
            queue_item=row,
            derivative={},
        ):
            return True
    return False
