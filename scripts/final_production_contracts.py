"""Pure contracts shared by the final production preparation commands.

Nothing here performs a network request or a Sheets mutation.  The functions
make optional X acquisition, permission gaps, canary evidence and activation
requirements explicit rather than treating an unavailable integration as a
successful post.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
    LEGACY_CANARY_TYPES,
    TEXT_ACTIVATION_CANARY_TYPES,
    activation_canary_id,
    activation_slot,
    canonical_activation_type,
)

ROOT = Path(__file__).resolve().parents[1]
# Backward-compatible runtime subtype export.
# Activation code uses ACTIVATION_CANARY_TYPES.
CANARY_TYPES = LEGACY_CANARY_TYPES

APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}


def is_individual_source_post_url(platform: str, url: str) -> bool:
    """Accept only a concrete external post/video URL for each supported source."""
    parsed = urlsplit(str(url).strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    platform = str(platform).lower()
    if not platform:
        if "youtube" in host or host == "youtu.be":
            platform = "youtube"
        elif host.endswith("tiktok.com"):
            platform = "tiktok"
        elif host.endswith("threads.com"):
            platform = "threads"
        elif host in {"x.com", "twitter.com"}:
            platform = "x"
    if platform == "youtube":
        return (
            (
                host in {"youtube.com", "m.youtube.com"}
                and path == "/watch"
                and bool(parse_qs(parsed.query).get("v"))
            )
            or (host == "youtu.be" and bool(path.strip("/")))
            or (host == "youtube.com" and path.startswith("/shorts/"))
        )
    if platform == "tiktok":
        return (
            host.endswith("tiktok.com")
            and "/video/" in path
            and bool(path.rsplit("/video/", 1)[-1])
        )
    if platform == "threads":
        return host.endswith("threads.com") and "/post/" in path
    if platform == "x":
        return host in {"x.com", "twitter.com"} and "/status/" in path
    return False


def truthy(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def canary_id(account_id: str, canary_type: str) -> str:
    return f"canary_{account_id}_{canary_type}"


def is_active_permission(row: dict[str, Any], *, account_id: str, operation: str) -> bool:
    if str(row.get("account_id", "")) != account_id:
        return False
    if str(row.get("permission_status", "")).lower() != "approved":
        return False
    if str(row.get("rights_status", "")).lower() not in APPROVED_RIGHTS:
        return False
    if truthy(row.get("revoked")) or not str(row.get("evidence_reference", "")).strip():
        return False
    expires_at = str(row.get("expires_at", "")).strip()
    if expires_at:
        try:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                return False
        except ValueError:
            return False
    field = {
        "direct": "allow_original_repost",
        "clip": "allow_clip_repost",
        "download": "allow_download",
        "upload": "allow_cloudinary_storage",
    }.get(operation, "")
    return bool(field and truthy(row.get(field)))


def permission_deficits(
    sources: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source in sources:
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        for account_id in targets:
            if account_id not in ACCOUNTS:
                continue
            source_id = str(source.get("source_id", ""))
            platform = str(source.get("source_platform") or source.get("platform") or "").lower()
            if platform not in {"threads", "youtube", "tiktok", "x"}:
                continue
            direct_ok = any(
                str(p.get("source_id", "")) == source_id
                and is_active_permission(p, account_id=account_id, operation="direct")
                for p in permissions
            )
            clip_ok = any(
                str(p.get("source_id", "")) == source_id
                and is_active_permission(p, account_id=account_id, operation="clip")
                for p in permissions
            )
            if not direct_ok:
                rows.append(
                    {
                        "account_id": account_id,
                        "source_id": source_id,
                        "requirement": "direct_media_permission",
                        "reason": "active_evidence_bearing_direct_permission_missing",
                    }
                )
            if platform in {"youtube", "tiktok"} and not clip_ok:
                rows.append(
                    {
                        "account_id": account_id,
                        "source_id": source_id,
                        "requirement": "approved_source_clip_permission",
                        "reason": "active_evidence_bearing_clip_permission_missing",
                    }
                )
    return rows


def canary_required_permission_deficits(
    permissions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return only route-level media permission deficits."""

    rows: list[dict[str, str]] = []

    for account_id in ACCOUNTS:
        for canary_type, operation in (
            (
                "direct_reference_media",
                "direct",
            ),
            (
                "approved_source_clip",
                "clip",
            ),
        ):
            active = any(
                is_active_permission(
                    item,
                    account_id=account_id,
                    operation=operation,
                )
                for item in permissions
            )

            if active:
                continue

            rows.append(
                {
                    "canary_id": (
                        activation_canary_id(
                            account_id,
                            canary_type,
                        )
                    ),
                    "account_id": account_id,
                    "canary_type": canary_type,
                    "operation": operation,
                    "reason": (
                        "active_evidence_bearing_"
                        "permission_missing_for_canary"
                    ),
                }
            )

    return {
        "scope": (
            "four_route_level_media_"
            "canary_slots_only"
        ),
        "required_slot_count": 4,
        "deficit_count": len(rows),
        "deficits": rows,
    }



def source_integrity_report(
    parents: list[dict[str, Any]],
    children: list[dict[str, Any]],
    *,
    source_ids: set[str] | None = None,
) -> dict[str, Any]:
    relevant = [
        row for row in parents if not source_ids or str(row.get("source_id", "")) in source_ids
    ]
    by_id = {str(row.get("source_post_id", "")): row for row in relevant}
    failures: list[dict[str, str]] = []
    for child in children:
        parent_id = str(child.get("source_post_id", ""))
        parent = by_id.get(parent_id)
        if not parent:
            continue
        if str(child.get("canonical_post_url", "")) != str(parent.get("canonical_post_url", "")):
            failures.append({"source_post_id": parent_id, "reason": "child_parent_url_mismatch"})
        try:
            index = int(child.get("media_index", ""))
            if index < 0:
                failures.append({"source_post_id": parent_id, "reason": "negative_media_index"})
        except (TypeError, ValueError):
            failures.append({"source_post_id": parent_id, "reason": "media_index_missing"})
    for parent_id, parent in by_id.items():
        url = str(parent.get("canonical_post_url", ""))
        if not is_individual_source_post_url(str(parent.get("platform", "")), url):
            failures.append({"source_post_id": parent_id, "reason": "parent_not_individual_post"})
    return {
        "status": "NO_EVIDENCE" if not by_id else "PASS" if not failures else "FAIL",
        "parent_count": len(by_id),
        "child_count": sum(1 for row in children if str(row.get("source_post_id", "")) in by_id),
        "failures": failures[:100],
    }


def canary_source_integrity_report(
    datasets: dict[
        str,
        list[dict[str, Any]],
    ],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify selected route-level canary sources."""

    parents = {
        str(
            row.get(
                "source_post_id",
                "",
            )
        ): row
        for row in datasets.get(
            "source_posts",
            [],
        )
    }

    children_by_parent: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for child in datasets.get(
        "source_post_media",
        [],
    ):
        children_by_parent.setdefault(
            str(
                child.get(
                    "source_post_id",
                    "",
                )
            ),
            [],
        ).append(child)

    checks: list[dict[str, Any]] = []

    for candidate in candidates:
        account_id = str(
            candidate.get(
                "account_id",
                "",
            )
        )

        kind = canonical_activation_type(
            candidate.get(
                "canary_type",
                "",
            ),
            content_route=candidate.get(
                "content_route",
                "",
            ),
        )

        canonical_id = (
            activation_canary_id(
                account_id,
                kind,
            )
            if kind
            else str(
                candidate.get(
                    "canary_id",
                    "",
                )
            )
        )

        reasons: list[str] = []

        if not kind:
            reasons.append(
                "unknown_activation_route"
            )

        if kind in (
            TEXT_ACTIVATION_CANARY_TYPES
        ):
            checks.append(
                {
                    "canary_id": canonical_id,
                    "account_id": account_id,
                    "canary_type": kind,
                    "status": (
                        "PASS"
                        if not reasons
                        else "FAIL"
                    ),
                    "scope": (
                        "no_external_source_"
                        "parent_required"
                    ),
                    "reasons": sorted(
                        set(reasons)
                    ),
                }
            )
            continue

        if kind == "approved_source_clip":
            if not str(
                candidate.get(
                    "source_video_id",
                    "",
                )
            ).strip():
                reasons.append(
                    "source_video_id_missing"
                )

            if not str(
                candidate.get(
                    "clip_candidate_id",
                    "",
                )
            ).strip():
                reasons.append(
                    "clip_candidate_id_missing"
                )

            if not str(
                candidate.get(
                    "media_url",
                    "",
                )
                or candidate.get(
                    "local_path",
                    "",
                )
            ).strip():
                reasons.append(
                    "clip_media_missing"
                )

            if (
                str(
                    candidate.get(
                        "permission_status",
                        "",
                    )
                ).lower()
                != "approved"
                or str(
                    candidate.get(
                        "rights_status",
                        "",
                    )
                ).lower()
                not in APPROVED_RIGHTS
                or not str(
                    candidate.get(
                        "permission_evidence",
                        "",
                    )
                ).strip()
            ):
                reasons.append(
                    "permission_evidence_"
                    "missing_or_inactive"
                )

            checks.append(
                {
                    "canary_id": canonical_id,
                    "account_id": account_id,
                    "canary_type": kind,
                    "status": (
                        "PASS"
                        if not reasons
                        else "FAIL"
                    ),
                    "scope": (
                        "approved_source_clip"
                    ),
                    "reasons": sorted(
                        set(reasons)
                    ),
                }
            )
            continue

        source_post_id = str(
            candidate.get(
                "source_post_id",
                "",
            )
        ).strip()

        parent = parents.get(
            source_post_id
        )

        if not source_post_id or not parent:
            reasons.append(
                "source_post_missing"
            )
        else:
            platform = str(
                parent.get("platform")
                or parent.get(
                    "source_platform"
                )
                or ""
            )

            parent_url = str(
                parent.get(
                    "canonical_post_url",
                    "",
                )
            )

            if not is_individual_source_post_url(
                platform,
                parent_url,
            ):
                reasons.append(
                    "parent_not_individual_post"
                )

            children = (
                children_by_parent.get(
                    source_post_id,
                    [],
                )
            )

            if not children:
                reasons.append(
                    "source_post_media_missing"
                )

            linked_urls = {
                str(
                    child.get(
                        "storage_url",
                        "",
                    )
                ).strip()
                for child in children
            } | {
                str(
                    child.get(
                        "original_media_url",
                        "",
                    )
                ).strip()
                for child in children
            }

            linked_urls.discard("")

            candidate_urls: list[str] = []

            single_url = str(
                candidate.get(
                    "media_url",
                    "",
                )
            ).strip()

            if single_url:
                candidate_urls.append(
                    single_url
                )

            multiple = candidate.get(
                "media_urls",
                [],
            )

            if isinstance(
                multiple,
                list,
            ):
                candidate_urls.extend(
                    str(item).strip()
                    for item in multiple
                    if str(item).strip()
                )

            if not candidate_urls:
                reasons.append(
                    "direct_media_missing"
                )

            for media_url in (
                candidate_urls
            ):
                if (
                    media_url
                    not in linked_urls
                ):
                    reasons.append(
                        "direct_media_not_linked_"
                        "to_source_post_media"
                    )

            for child in children:
                if (
                    str(
                        child.get(
                            "canonical_post_url",
                            "",
                        )
                    )
                    != parent_url
                ):
                    reasons.append(
                        "child_parent_url_mismatch"
                    )

        if (
            str(
                candidate.get(
                    "permission_status",
                    "",
                )
            ).lower()
            != "approved"
            or str(
                candidate.get(
                    "rights_status",
                    "",
                )
            ).lower()
            not in APPROVED_RIGHTS
            or not str(
                candidate.get(
                    "permission_evidence",
                    "",
                )
            ).strip()
        ):
            reasons.append(
                "permission_evidence_"
                "missing_or_inactive"
            )

        checks.append(
            {
                "canary_id": canonical_id,
                "account_id": account_id,
                "canary_type": kind,
                "source_post_id": (
                    source_post_id
                ),
                "status": (
                    "PASS"
                    if not reasons
                    else "FAIL"
                ),
                "reasons": sorted(
                    set(reasons)
                ),
            }
        )

    failures = [
        check
        for check in checks
        if check["status"] != "PASS"
    ]

    return {
        "status": (
            "PASS"
            if checks and not failures
            else "FAIL"
        ),
        "checked_canary_count": len(
            checks
        ),
        "failures": failures,
        "checks": checks,
    }



def _canary_slot(
    row: dict[str, Any],
) -> tuple[str, str] | None:
    """Resolve one canonical activation route."""

    return activation_slot(row)



def activation_evidence(
    posted_results: list[dict[str, Any]],
    metric_jobs: list[dict[str, Any]],
    *,
    canary_integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Require valid source integrity, one verified post, and all metric windows.

    Batch-specific canary IDs are accepted, but metrics must belong to the
    exact verified canary ID. When an integrity report is supplied, canaries
    whose selected source bundle failed integrity are excluded from verified
    evidence rather than merely reported alongside it.
    """

    expected_slots = {
        (
            account_id,
            kind,
        )
        for account_id in ACCOUNTS
        for kind in ACTIVATION_CANARY_TYPES
    }

    integrity_required = canary_integrity is not None

    integrity_pass_slots: set[tuple[str, str]] = set()

    integrity_failures: list[dict[str, Any]] = []

    if integrity_required:
        for check in list(
            canary_integrity.get(
                "checks",
                [],
            )
        ):
            slot = _canary_slot(check)

            if slot not in expected_slots:
                continue

            if (
                str(
                    check.get(
                        "status",
                        "",
                    )
                ).upper()
                == "PASS"
            ):
                integrity_pass_slots.add(slot)
            else:
                integrity_failures.append(dict(check))

    verified_by_slot: dict[
        tuple[str, str],
        set[str],
    ] = {}

    for row in posted_results:
        slot = _canary_slot(row)

        candidate = str(
            row.get(
                "canary_id",
                "",
            )
        ).strip()

        if slot not in expected_slots or not candidate:
            continue

        if integrity_required and slot not in integrity_pass_slots:
            continue

        if (
            str(
                row.get(
                    "status",
                    "",
                )
            ).upper()
            != "POSTED"
        ):
            continue

        if (
            not str(
                row.get(
                    "post_url",
                    "",
                )
            ).strip()
            or not str(
                row.get(
                    "external_post_id",
                    "",
                )
            ).strip()
        ):
            continue

        if str(
            row.get(
                "verification_status",
                "",
            )
        ).upper() not in {
            "PASS",
            "VERIFIED",
            "READ_AFTER_WRITE_PASS",
        }:
            continue

        verified_by_slot.setdefault(
            slot,
            set(),
        ).add(candidate)

    metrics_by_canary: dict[
        str,
        set[int],
    ] = {}

    for row in metric_jobs:
        candidate = str(
            row.get(
                "canary_id",
                "",
            )
        ).strip()

        try:
            window = int(
                row.get(
                    "window_hours",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if candidate and str(
            row.get(
                "status",
                "",
            )
        ).upper() not in {
            "CANCELLED",
            "FAILED",
        }:
            metrics_by_canary.setdefault(
                candidate,
                set(),
            ).add(window)

    required_windows = {
        24,
        72,
        168,
    }

    missing_integrity = sorted(
        canary_id(
            account,
            kind,
        )
        for account, kind in expected_slots
        if (
            integrity_required
            and (
                account,
                kind,
            )
            not in integrity_pass_slots
        )
    )

    missing_posts = sorted(
        canary_id(
            account,
            kind,
        )
        for account, kind in expected_slots
        if not verified_by_slot.get(
            (
                account,
                kind,
            )
        )
    )

    missing_metrics: list[str] = []

    selected_evidence: dict[
        str,
        str,
    ] = {}

    for account, kind in sorted(expected_slots):
        slot_name = canary_id(
            account,
            kind,
        )

        candidates = sorted(
            verified_by_slot.get(
                (
                    account,
                    kind,
                ),
                set(),
            )
        )

        complete = [
            candidate
            for candidate in candidates
            if required_windows
            <= metrics_by_canary.get(
                candidate,
                set(),
            )
        ]

        if complete:
            selected_evidence[slot_name] = complete[-1]

        elif candidates:
            missing_metrics.append(slot_name)

    integrity_ready = not integrity_required or not missing_integrity

    delivery_ready = integrity_ready and not missing_posts

    content_ready = delivery_ready and not missing_metrics

    return {
        "status": ("READY_FOR_ACTIVATION" if content_ready else "BLOCKED"),
        "DELIVERY_READY": ("YES" if delivery_ready else "NO"),
        "CONTENT_READY": ("YES" if content_ready else "NO"),
        "AUTONOMOUS_PRODUCTION_READY": "NO",
        "expected_canary_count": len(expected_slots),
        "verified_canary_count": len(verified_by_slot),
        "integrity_verified_canary_count": (
            len(integrity_pass_slots) if integrity_required else None
        ),
        "selected_evidence_canary_ids": (selected_evidence),
        "missing_or_invalid_canary_source_integrity": (missing_integrity),
        "invalid_canary_source_integrity": (integrity_failures),
        "canary_source_integrity_status": (
            str(
                canary_integrity.get(
                    "status",
                    "FAIL",
                )
            )
            if integrity_required
            else "NOT_EVALUATED"
        ),
        "missing_posted_read_after_write": (missing_posts),
        "missing_metric_windows": (missing_metrics),
    }


def required_owner_inputs(
    deficits: list[dict[str, str]],
) -> dict[str, Any]:
    """Describe only current route-level media inputs."""

    needs: list[dict[str, Any]] = []

    for account_id in ACCOUNTS:
        needs.extend(
            [
                {
                    "input_id": (
                        f"{account_id}_"
                        "direct_reference_media"
                    ),
                    "account_id": account_id,
                    "canary_type": (
                        "direct_reference_media"
                    ),
                    "required": [
                        (
                            "one individual "
                            "source-post URL"
                        ),
                        (
                            "approved original "
                            "media URL or file"
                        ),
                        (
                            "media_permissions "
                            "evidence"
                        ),
                        (
                            "Threads original "
                            "repost permission"
                        ),
                    ],
                    "preference": (
                        "video first; image or "
                        "carousel may be runtime "
                        "fallbacks"
                    ),
                },
                {
                    "input_id": (
                        f"{account_id}_"
                        "approved_source_clip"
                    ),
                    "account_id": account_id,
                    "canary_type": (
                        "approved_source_clip"
                    ),
                    "required": [
                        (
                            "individual owned or "
                            "licensed video URL"
                        ),
                        "permission evidence",
                        "allowed clip range",
                        (
                            "Threads clip repost "
                            "permission"
                        ),
                    ],
                },
            ]
        )

    return {
        "schema_version": 2,
        "purpose": (
            "route-level final media canary "
            "inputs; no permission is inferred"
        ),
        "permission_deficits": deficits,
        "required_owner_inputs": needs,
    }
