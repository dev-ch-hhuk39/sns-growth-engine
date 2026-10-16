"""Immutable product-level posting scope; runtime env cannot grant X posting.

Enable a new social platform only via separately reviewed code, provider
authorization, release and end-to-end canary, not an operator .env flag.
"""
from __future__ import annotations

ACTIVE_REAL_PUBLISH_PLATFORMS = frozenset({"threads"})


def allowed_for_real_post(platform: str) -> bool:
    return platform.lower() in ACTIVE_REAL_PUBLISH_PLATFORMS
