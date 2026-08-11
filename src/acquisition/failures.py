"""Stable operator-facing acquisition failure taxonomy."""
from __future__ import annotations

from enum import StrEnum


class FailureCategory(StrEnum):
    TOOL_NOT_INSTALLED = "TOOL_NOT_INSTALLED"
    TOOL_UNHEALTHY = "TOOL_UNHEALTHY"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    PROFILE_DISCOVERY_UNAVAILABLE = "PROFILE_DISCOVERY_UNAVAILABLE"
    POST_DISCOVERY_UNAVAILABLE = "POST_DISCOVERY_UNAVAILABLE"
    POST_DETAIL_UNAVAILABLE = "POST_DETAIL_UNAVAILABLE"
    VIDEO_URL_EXTRACTION_UNAVAILABLE = "VIDEO_URL_EXTRACTION_UNAVAILABLE"
    MEDIA_NOT_FOUND = "MEDIA_NOT_FOUND"
    NO_VIDEO_FOUND_IN_BOUNDED_SAMPLE = "NO_VIDEO_FOUND_IN_BOUNDED_SAMPLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    BROWSER_REQUIRED = "BROWSER_REQUIRED"
    COOKIE_REQUIRED = "COOKIE_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    HTTP_BLOCKED = "HTTP_BLOCKED"
    PRIVATE_SOURCE = "PRIVATE_SOURCE"
    AUTHOR_MISMATCH = "AUTHOR_MISMATCH"
    RIGHTS_BLOCKED = "RIGHTS_BLOCKED"
    THIRD_PARTY_REPOST = "THIRD_PARTY_REPOST"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    INVALID_MEDIA = "INVALID_MEDIA"
    BACKEND_UNSTABLE = "BACKEND_UNSTABLE"
    LICENSE_REJECTED = "LICENSE_REJECTED"
    OPAQUE_EXTERNAL_SERVICE_REJECTED = "OPAQUE_EXTERNAL_SERVICE_REJECTED"


NON_FALLBACK_FAILURES = {
    FailureCategory.AUTHOR_MISMATCH,
    FailureCategory.RIGHTS_BLOCKED,
    FailureCategory.THIRD_PARTY_REPOST,
    FailureCategory.PRIVATE_SOURCE,
    FailureCategory.LICENSE_REJECTED,
    FailureCategory.OPAQUE_EXTERNAL_SERVICE_REJECTED,
}


def classify_failure(platform: str, reason: str) -> FailureCategory:
    text = str(reason or "").lower()
    markers = (
        (("not_installed", "not found", "missing_tool"), FailureCategory.TOOL_NOT_INSTALLED),
        (("unsupported_platform",), FailureCategory.UNSUPPORTED_PLATFORM),
        (("browser_required", "playwright_required"), FailureCategory.BROWSER_REQUIRED),
        (("cookie_required", "explicit_cookie_required"), FailureCategory.COOKIE_REQUIRED),
        (("401", "403", "auth_required", "login_required"), FailureCategory.AUTH_REQUIRED),
        (("429", "rate_limit"), FailureCategory.RATE_LIMITED),
        (("http_blocked", "captcha", "access denied"), FailureCategory.HTTP_BLOCKED),
        (("private_source", "private account"), FailureCategory.PRIVATE_SOURCE),
        (("author_mismatch",), FailureCategory.AUTHOR_MISMATCH),
        (("third_party_repost",), FailureCategory.THIRD_PARTY_REPOST),
        (("rights_blocked", "permission_blocked"), FailureCategory.RIGHTS_BLOCKED),
        (("license_rejected",), FailureCategory.LICENSE_REJECTED),
        (("opaque_external_service",), FailureCategory.OPAQUE_EXTERNAL_SERVICE_REJECTED),
        (("invalid_media", "ffprobe_failed", "no_video_stream"), FailureCategory.INVALID_MEDIA),
        (("download_failed",), FailureCategory.DOWNLOAD_FAILED),
        (("no_video", "no videos"), FailureCategory.NO_VIDEO_FOUND_IN_BOUNDED_SAMPLE),
        (("video_url", "post_detail"), FailureCategory.VIDEO_URL_EXTRACTION_UNAVAILABLE),
        (("individual_posts_unavailable", "post_links", "secondary user id", "discovery_failed", "profile_application_404"), FailureCategory.POST_DISCOVERY_UNAVAILABLE),
        (("profile_url_required", "profile_discovery"), FailureCategory.PROFILE_DISCOVERY_UNAVAILABLE),
        (("media_not_found",), FailureCategory.MEDIA_NOT_FOUND),
        (("tool_unhealthy",), FailureCategory.TOOL_UNHEALTHY),
    )
    for values, category in markers:
        if any(value in text for value in values):
            return category
    if platform == "threads" and "public_http_failed" in text:
        return FailureCategory.PROFILE_DISCOVERY_UNAVAILABLE
    return FailureCategory.BACKEND_UNSTABLE


def fallback_allowed(category: FailureCategory | str) -> bool:
    return FailureCategory(category) not in NON_FALLBACK_FAILURES
