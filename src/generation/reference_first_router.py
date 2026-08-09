"""Shared, reference-first content-route selection for operational accounts.

The router deliberately separates the choice of *format* from persona writing.
Night Scout and Liver Manager provide different audience/persona inputs later in
generation, but use the same source-understanding and route-safety contract.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MIX_PATH = ROOT / "config" / "content_mix" / "default_mix.json"

REFERENCE_FIRST_ROUTES = (
    "reference_text_generation",
    "direct_reference_media",
    "pdca_text_generation",
    "new_text_generation",
    "approved_source_clip",
)
CLIP_ROUTE = "approved_source_clip"


def load_operational_mix(account_id: str, *, config: dict[str, Any] | None = None) -> dict[str, int]:
    """Return the account's enforced Threads mix and reject malformed ratios."""
    if config is None:
        config = json.loads(MIX_PATH.read_text(encoding="utf-8"))
    policy = config.get("operational_threads_slot_mix", {})
    ratios = {name: int(value) for name, value in policy.get(account_id, {}).items()}
    if set(ratios) != set(REFERENCE_FIRST_ROUTES) or sum(ratios.values()) != 100:
        raise ValueError("reference_first_mix_must_contain_all_routes_and_sum_to_100")
    if ratios[CLIP_ROUTE] > 5:
        raise ValueError("clip_route_must_not_exceed_five_percent")
    if ratios["reference_text_generation"] + ratios["direct_reference_media"] < 65:
        raise ValueError("reference_and_quote_routes_must_be_primary")
    return ratios


def clip_eligibility(content_understanding: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Only permit a clip after the whole source has been understood.

    A video merely being available, or having a transcript, never makes it a
    clip.  The analysis must explicitly establish a self-contained segment.
    """
    item = content_understanding or {}
    reasons: list[str] = []
    if str(item.get("status", "")).upper() != "PASS":
        reasons.append("content_understanding_not_passed")
    if str(item.get("transcript_status", "")).upper() not in {"PASS", "AVAILABLE"}:
        reasons.append("transcript_not_available")
    if not bool(item.get("standalone_segment_confirmed")):
        reasons.append("standalone_segment_not_confirmed")
    try:
        score = float(item.get("standalone_story_score", 0))
    except (TypeError, ValueError):
        score = 0
    if score < 85:
        reasons.append("standalone_story_score_below_threshold")
    if not bool(item.get("clip_worthy")):
        reasons.append("clip_worthiness_not_confirmed")
    return not reasons, reasons


def choose_reference_first_route(
    *,
    desired_route: str,
    source_has_direct_media_permission: bool,
    content_understanding: dict[str, Any] | None = None,
    has_reference_post: bool = True,
    has_measured_pdca_signal: bool = False,
) -> dict[str, Any]:
    """Select a route after source understanding, without media-to-text fallback.

    Direct-media requests stay blocked when no approved direct media is
    available.  Clip requests may only become clips with positive evidence; a
    video without that evidence is explicitly routed to direct quote/comment
    when permitted, rather than being cut speculatively.
    """
    if desired_route not in REFERENCE_FIRST_ROUTES:
        return {"status": "BLOCKED", "route": "", "reasons": ["unknown_content_route"]}
    if desired_route == CLIP_ROUTE:
        eligible, reasons = clip_eligibility(content_understanding)
        if eligible:
            return {"status": "PASS", "route": CLIP_ROUTE, "reasons": [], "clip_eligible": True}
        if source_has_direct_media_permission:
            return {
                "status": "PASS",
                "route": "direct_reference_media",
                "reasons": reasons,
                "clip_eligible": False,
                "selection_reason": "video_is_better_as_direct_quote_than_a_forced_clip",
            }
        return {"status": "BLOCKED", "route": "", "reasons": reasons + ["direct_media_permission_missing"], "clip_eligible": False}
    if desired_route == "direct_reference_media":
        if source_has_direct_media_permission:
            return {"status": "PASS", "route": desired_route, "reasons": [], "clip_eligible": False}
        return {"status": "BLOCKED", "route": "", "reasons": ["direct_media_permission_missing"], "clip_eligible": False}
    if desired_route == "reference_text_generation" and not has_reference_post:
        return {"status": "BLOCKED", "route": "", "reasons": ["reference_post_missing"], "clip_eligible": False}
    if desired_route == "pdca_text_generation" and not has_measured_pdca_signal:
        return {"status": "BLOCKED", "route": "", "reasons": ["measured_pdca_signal_missing"], "clip_eligible": False}
    return {"status": "PASS", "route": desired_route, "reasons": [], "clip_eligible": False}
