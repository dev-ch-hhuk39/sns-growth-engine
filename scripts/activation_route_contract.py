#!/usr/bin/env python3
"""Canonical activation routes, separate from runtime media subtypes."""

from __future__ import annotations

from typing import Any

ACCOUNTS = (
    "night_scout",
    "liver_manager",
)

ACTIVATION_CANARY_TYPES = (
    "original_text",
    "reference_text",
    "direct_reference_media",
    "approved_source_clip",
    "pdca_text",
)

TEXT_ACTIVATION_CANARY_TYPES = {
    "original_text",
    "reference_text",
    "pdca_text",
}

MEDIA_ACTIVATION_CANARY_TYPES = {
    "direct_reference_media",
    "approved_source_clip",
}

LEGACY_DIRECT_MEDIA_TYPES = {
    "direct_image",
    "direct_video",
    "direct_carousel",
}

LEGACY_CANARY_TYPES = (
    "original_text",
    "reference_text",
    "direct_image",
    "direct_video",
    "direct_carousel",
    "approved_source_clip",
)

_ALIASES = {
    "original_hypothesis": "original_text",
    "autonomous_original": "original_text",
    "original_text": "original_text",
    "reference_based": "reference_text",
    "manual_reference": "reference_text",
    "reference_text": "reference_text",
    "direct_reference_media": (
        "direct_reference_media"
    ),
    "saved_direct_reference_media": (
        "direct_reference_media"
    ),
    "approved_source_clip": (
        "approved_source_clip"
    ),
    "saved_approved_source_clip": (
        "approved_source_clip"
    ),
    "pdca": "pdca_text",
    "pdca_text": "pdca_text",
}


def canonical_activation_type(
    value: Any = "",
    *,
    content_route: Any = "",
) -> str:
    """Return one canonical scheduled activation route."""

    route = str(content_route or "").strip().lower()

    if route in ACTIVATION_CANARY_TYPES:
        return route

    if route in LEGACY_DIRECT_MEDIA_TYPES:
        return "direct_reference_media"

    raw = str(value or "").strip().lower()

    if raw in LEGACY_DIRECT_MEDIA_TYPES:
        return "direct_reference_media"

    return _ALIASES.get(raw, "")


def activation_canary_id(
    account_id: str,
    canary_type: str,
) -> str:
    return (
        f"canary_{account_id}_{canary_type}"
    )


def activation_slot(
    row: dict[str, Any],
) -> tuple[str, str] | None:
    """Resolve canonical route from fields or canary ID."""

    account_id = str(
        row.get("account_id")
        or row.get("target_account_id")
        or ""
    ).strip()

    kind = canonical_activation_type(
        row.get("canary_type")
        or row.get("content_type")
        or row.get("generation_mode")
        or "",
        content_route=row.get(
            "content_route",
            "",
        ),
    )

    if (
        account_id in ACCOUNTS
        and kind in ACTIVATION_CANARY_TYPES
    ):
        return account_id, kind

    candidate = str(
        row.get("canary_id", "")
    ).strip()

    for expected_account in ACCOUNTS:
        for expected_kind in (
            ACTIVATION_CANARY_TYPES
        ):
            if (
                candidate
                == activation_canary_id(
                    expected_account,
                    expected_kind,
                )
                or candidate.endswith(
                    f"_{expected_account}_"
                    f"{expected_kind}"
                )
            ):
                return (
                    expected_account,
                    expected_kind,
                )

        for legacy_kind in (
            LEGACY_DIRECT_MEDIA_TYPES
        ):
            if (
                candidate.endswith(
                    f"_{expected_account}_"
                    f"{legacy_kind}"
                )
            ):
                return (
                    expected_account,
                    "direct_reference_media",
                )

    return None
