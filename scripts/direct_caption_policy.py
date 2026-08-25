#!/usr/bin/env python3
"""Pure caption-mode policy for approved Direct media."""
from __future__ import annotations

from typing import Any, Mapping

VALID_DIRECT_CAPTION_MODES = {"source_copyedit", "transform"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _true(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "pass"}


def direct_caption_mode(
    *,
    post: Mapping[str, Any],
    source: Mapping[str, Any] | None = None,
    permission: Mapping[str, Any] | None = None,
) -> str:
    """Return transform only for approved owned or registered-source commentary.

    Unregistered external creator media remains source-preserving by default.
    Registered source commentary requires the canonical owner scope and its
    provenance controls; the function never infers permission from public text.
    """

    source = source or {}
    permission = permission or {}

    for row in (permission, post, source):
        for field in (
            "direct_caption_mode",
            "caption_mode",
            "transformation_type",
        ):
            explicit = _text(row.get(field)).lower()
            if explicit in VALID_DIRECT_CAPTION_MODES:
                return explicit

    source_id = _text(
        post.get("source_id")
        or source.get("source_id")
        or permission.get("source_id")
    )
    rights = {
        _text(row.get("rights_status")).lower()
        for row in (permission, post, source)
        if _text(row.get("rights_status"))
    }
    ownership = {
        _text(row.get("ownership") or row.get("source_type")).lower()
        for row in (permission, post, source)
        if _text(row.get("ownership") or row.get("source_type"))
    }
    owned = (
        "owned" in rights
        or "owned" in ownership
        or "system_owned" in ownership
        or source_id.startswith("system_owned_")
    )
    allow_new_caption = any(
        _true(row.get("allow_new_caption"))
        for row in (permission, post, source)
    )
    # Direct reference media is source preserving by default. Registry
    # approval authorizes the media use; it does not silently authorize a
    # large-angle editorial transform. An explicit caption mode remains the
    # only way to request transform for a registered external source.
    return "transform" if owned and allow_new_caption else "source_copyedit"


def queue_caption_mode(
    queue_row: Mapping[str, Any],
    *,
    direct_reference: bool,
) -> str:
    """Read persisted mode without changing legacy Direct behavior."""

    for field in (
        "caption_mode",
        "transformation_type",
        "source_generation_mode",
    ):
        explicit = _text(queue_row.get(field)).lower()
        if explicit in VALID_DIRECT_CAPTION_MODES:
            return explicit
    return "source_copyedit" if direct_reference else "transform"
