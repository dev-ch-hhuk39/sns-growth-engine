"""Shared rights policy for reference/media workflows.

This module is intentionally small and dependency-free so CLIs can use the
same vocabulary before any download, cut, upload, or post queue step.
"""
from __future__ import annotations

from dataclasses import dataclass

THIRD_PARTY_REFERENCE_ONLY = "third_party_reference_only"
UNKNOWN = "unknown"

APPROVED_MEDIA_RIGHTS = frozenset({"owned", "licensed", "approved_creator_clip"})
REFERENCE_ANALYSIS_RIGHTS = frozenset({
    THIRD_PARTY_REFERENCE_ONLY,
    "reference_only",
    UNKNOWN,
    *APPROVED_MEDIA_RIGHTS,
})
BLOCKED_MEDIA_RIGHTS = frozenset({THIRD_PARTY_REFERENCE_ONLY, "reference_only", UNKNOWN, "restricted", "not_allowed"})


@dataclass(frozen=True)
class RightsDecision:
    """A serializable decision used by CLI plans and tests."""

    rights_status: str
    action: str
    allowed: bool
    reference_analysis_allowed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "rights_status": self.rights_status,
            "action": self.action,
            "allowed": self.allowed,
            "reference_analysis_allowed": self.reference_analysis_allowed,
            "reason": self.reason,
        }


def normalize_rights_status(value: object) -> str:
    status = str(value or UNKNOWN).strip().lower()
    if status == "allowed":
        return "approved_creator_clip"
    if status in {"", "none"}:
        return UNKNOWN
    return status


def rights_allows_reference_analysis(rights_status: object) -> bool:
    return normalize_rights_status(rights_status) in REFERENCE_ANALYSIS_RIGHTS


def rights_allows_media_use(rights_status: object) -> bool:
    return normalize_rights_status(rights_status) in APPROVED_MEDIA_RIGHTS


def rights_block_reason(rights_status: object, action: str) -> str:
    status = normalize_rights_status(rights_status)
    if status == UNKNOWN:
        return f"{action} requires human rights approval; rights_status=unknown is blocked"
    if status in {THIRD_PARTY_REFERENCE_ONLY, "reference_only"}:
        return f"third-party/reference-only media cannot be {action}"
    if status in {"restricted", "not_allowed"}:
        return f"{action} is blocked by rights_status={status}"
    return f"{action} requires rights_status owned/licensed/approved_creator_clip"


def build_rights_decision(rights_status: object, action: str = "media_use") -> RightsDecision:
    status = normalize_rights_status(rights_status)
    allowed = rights_allows_media_use(status)
    return RightsDecision(
        rights_status=status,
        action=action,
        allowed=allowed,
        reference_analysis_allowed=rights_allows_reference_analysis(status),
        reason="" if allowed else rights_block_reason(status, action),
    )
