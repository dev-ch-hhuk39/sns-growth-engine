"""Fail-closed scoping rules for a staged trusted-review rollout.

Do not mistake a Sheets cell like "OK", "APPROVED" or "reviewer_id" for an
authenticated human decision. The strict policy is intentionally opt-in until
an authoritative reviewer identity + evidence backend exists.
"""
from __future__ import annotations

from typing import Any, Mapping

PROTECTED_MEDIA_SLOTS = frozenset({
    ("night_scout", "ns_1800_direct_media"),
    ("night_scout", "ns_2100_clip_media"),
    ("liver_manager", "lm_1600_direct_media"),
    ("liver_manager", "lm_1800_clip_media"),
})
PROTECTED_ACCOUNTS = frozenset({"night_scout", "liver_manager"})
MEDIA_TYPES = frozenset({"IMAGE", "VIDEO", "CAROUSEL"})
MEDIA_GENERATION_MODES = frozenset({
    "direct_reference_media", "approved_source_clip", "generated_clip",
    "hybrid_media", "video_clip",
})
TRUE_VALUES = frozenset({"true", "yes", "1"})


def _field(row: Mapping[str, Any], name: str) -> str:
    value = row.get(name)
    return str(value).strip() if isinstance(value, (str, int, float, bool)) else ""


def is_protected_media_candidate(row: Mapping[str, Any]) -> bool:
    """Detect target media even when a row omits the media_required flag.

    This is a best-effort legacy boundary, not proof of approval or rights.
    Unknown accounts are not covered by this phase's four media-slot policy.
    """
    if not isinstance(row, Mapping):
        return False
    account = _field(row, "account_id")
    if account not in PROTECTED_ACCOUNTS:
        return False
    slot = _field(row, "slot_id")
    if (account, slot) in PROTECTED_MEDIA_SLOTS:
        return True
    if _field(row, "media_required").lower() in TRUE_VALUES:
        return True
    if (_field(row, "media_type").upper() in MEDIA_TYPES
            or _field(row, "publisher_media_type").upper() in MEDIA_TYPES):
        return True
    if _field(row, "generation_mode").lower() in MEDIA_GENERATION_MODES:
        return True
    if any(_field(row, key) for key in (
        "media_asset_id", "media_url", "clip_candidate_id", "video_clip_id",
    )):
        return True
    return False


def requires_strict_review_block(
    row: Mapping[str, Any],
    *,
    desired_status: str,
    strict_trusted_media_review: bool,
) -> bool:
    """Block a legacy READY transition when strict rollout is enabled.

    The old Sheets/CLI paths cannot safely accept local JSON receipts or
    self-reported reviewer fields as authorization, so strict mode denies
    protected media READY promotions rather than attempting a bypass.
    """
    return (
        strict_trusted_media_review is True
        and str(desired_status).strip().upper() == "READY"
        and is_protected_media_candidate(row)
    )
