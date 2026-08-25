#!/usr/bin/env python3
"""Prioritize reliable, recent direct-media candidates."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import ingest_direct_reference_media as core  # noqa: E402

_CORE_PERMISSION_OK_FROM_ROWS = core.permission_ok_from_rows


_PLATFORM_PRIORITY = {
    # Keep the historically reliable X route first, but prefer registered
    # Threads/TikTok assets over YouTube on hosted runners.  Anonymous YouTube
    # downloads can be provider-blocked even when the PO Token provider itself
    # is healthy, so one provider must never consume the whole candidate budget.
    "x": 0,
    "threads": 1,
    "tiktok": 2,
    "youtube": 3,
}

EXTERNAL_UNAVAILABLE_RETRY_COOLDOWN_SECONDS = 6 * 60 * 60


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def external_unavailable_cooldown_active(
    media: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Do not immediately retry the same provider-blocked physical asset."""

    if str(media.get("download_status", "")).upper() != "SKIPPED_EXTERNAL_UNAVAILABLE":
        return False

    attempted_at = _parse_timestamp(
        media.get("last_attempt_at")
        or media.get("updated_at")
    )

    # Old rows without timing evidence remain skipped rather than burning the
    # current bounded run repeatedly. A later acquisition refresh can replace
    # the volatile media row.
    if attempted_at is None:
        return True

    current = now or datetime.now(timezone.utc)
    age = (current - attempted_at).total_seconds()

    return age < EXTERNAL_UNAVAILABLE_RETRY_COOLDOWN_SECONDS


def permission_ok_from_rows(
    rows: list[dict[str, Any]],
    source_id: str,
    account_id: str = "",
) -> bool:
    """Use the same strict ledger decision as the core ingestion path."""
    return _CORE_PERMISSION_OK_FROM_ROWS(rows, source_id, account_id)


def _looks_like_threads_placeholder(url: str) -> bool:
    lowered = str(url or "").lower()

    return any(
        marker in lowered
        for marker in (
            "static.cdninstagram.com/rsrc.php",
            "/t51.82787-19/",
            "/t51.2885-19/",
            "profile_pic",
        )
    )


def select_pending_media_id(
    client: Any,
    account_id: str,
    *,
    permissions: list[dict[str, Any]] | None = None,
) -> str:
    """Select a permitted real post asset without retrying known bad media."""

    permissions = (
        core.permission_rows(client)
        if permissions is None
        else permissions
    )

    posts = {
        str(row.get("source_post_id", "")): row
        for row in client._ws("source_posts").get_all_records()
    }

    understandings = (
        {
            str(row.get("source_post_media_id", "")): row
            for row in client._ws("source_media_understanding").get_all_records()
        }
        if core.truthy(
            os.environ.get(
                "ALLOW_LOCAL_TRANSCRIPTION"
            )
        )
        else {}
    )

    media_rows = client._ws(
        "source_post_media"
    ).get_all_records()
    media_by_post: dict[str, list[dict[str, Any]]] = {}

    for media in media_rows:
        media_by_post.setdefault(
            str(
                media.get(
                    "source_post_id",
                    "",
                )
            ),
            [],
        ).append(media)

    video_only_parent_ids = {
        source_post_id
        for source_post_id, bundle in media_by_post.items()
        if bundle
        and all(
            str(
                item.get(
                    "media_type",
                    "",
                )
            ).strip().lower()
            == "video"
            for item in bundle
        )
    }

    pending: list[tuple[int, str, str]] = []

    for media in media_rows:
        source_post_id = str(
            media.get(
                "source_post_id",
                "",
            )
        )

        # A direct comment slot is video-only. Reject image-only, mixed and
        # unknown bundles before downloading any child so a partial parent can
        # never enter Cloudinary or the review inventory.
        if source_post_id not in video_only_parent_ids:
            continue

        post = posts.get(
            source_post_id
        )

        if not post:
            continue

        if (
            str(
                post.get(
                    "target_account_id",
                    "",
                )
            )
            != account_id
        ):
            continue

        if not core.permission_ok_from_rows(
            permissions,
            str(
                post.get(
                    "source_id",
                    "",
                )
            ),
            account_id,
        ):
            continue

        media_id = str(media.get("source_post_media_id", ""))

        download_status = str(
            media.get(
                "download_status",
                "",
            )
        ).upper()

        # Provider/network unavailability is candidate-level fail-soft.  Do not
        # immediately select the same physical asset again merely because its
        # content-understanding row is still missing.
        if external_unavailable_cooldown_active(media):
            continue

        refresh_understanding = core.media_understanding_needs_refresh(
            media,
            understandings.get(media_id),
        )

        if (
            str(
                media.get(
                    "cloudinary_status",
                    "",
                )
            ).upper()
            == "UPLOADED"
            and str(
                media.get(
                    "storage_url",
                    "",
                )
            )
            and not refresh_understanding
        ):
            continue

        recoverable_identical_failure = (
            download_status == "FAILED"
            and str(
                media.get(
                    "understanding_status",
                    "",
                )
            ).upper()
            == "PASS"
            and bool(
                str(
                    media.get(
                        "understanding_id",
                        "",
                    )
                ).strip()
            )
            and str(
                media.get(
                    "last_error",
                    "",
                )
            )
            in {
                "ingest_failed:RuntimeError",
                "ingest_failed:media_asset_contract_conflict",
                "ingest_failed:identical_media_asset_contract_conflict",
            }
        )

        if (
            download_status
            in {
                "FAILED",
                "BLOCKED",
                "SKIPPED_EXTERNAL_UNAVAILABLE",
            }
            and not recoverable_identical_failure
            and not refresh_understanding
        ):
            continue

        url = str(
            media.get(
                "original_media_url",
            )
            or media.get(
                "canonical_post_url",
            )
            or ""
        )

        platform = str(
            post.get(
                "platform",
                "",
            )
        ).lower()

        if not core.can_attempt_physical_media(
            platform,
            str(media.get("original_media_url") or media.get("canonical_post_url") or ""),
        ):
            continue

        if platform == "youtube":
            if (
                "/watch" not in url
                and "/shorts/" not in url
            ):
                continue

        elif platform == "x":
            if "/status/" not in url:
                continue

        elif platform == "tiktok":
            if "/video/" not in url:
                continue

        elif platform == "threads":
            parent_url = str(
                media.get("canonical_post_url")
                or post.get("canonical_post_url")
                or ""
            )
            if "/post/" not in parent_url:
                continue
            if not core.safe_https_url(
                url,
                stream_url=True,
            ):
                continue

            if _looks_like_threads_placeholder(url):
                continue

        else:
            continue

        if not media_id:
            continue

        pending.append(
            (
                _PLATFORM_PRIORITY.get(
                    platform,
                    99,
                ),
                str(
                    media.get(
                        "created_at",
                        "",
                    )
                ),
                media_id,
            )
        )

    # First sort by newest item inside each platform.
    pending.sort(
        key=lambda item: (
            item[1],
            item[2],
        ),
        reverse=True,
    )

    # Stable sort then gives platform priority while preserving recency.
    pending.sort(
        key=lambda item: item[0]
    )

    return pending[0][2] if pending else ""


core.permission_ok_from_rows = permission_ok_from_rows
core.select_pending_media_id = select_pending_media_id


def main() -> int:
    """Try the next approved post after a failed automatic candidate.

    A partially ingested parent remains ineligible because the normal direct
    pipeline requires every ordered child to be uploaded and understood. The
    next attempt therefore selects another complete source post. Explicit ID
    invocations never change the operator-selected parent or media child.
    """
    explicit_target = any(
        flag in sys.argv for flag in ("--source-post-id", "--source-post-media-id")
    )
    configured = int(os.environ.get("DIRECT_MEDIA_CANDIDATE_ATTEMPTS", "3") or "3")
    max_attempts = 1 if explicit_target else max(1, min(configured, 3))
    final_status = ""
    for attempt in range(1, max_attempts + 1):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = core.main()
        rendered = output.getvalue()
        print(rendered, end="")
        try:
            payload = json.loads(rendered)
        except (json.JSONDecodeError, TypeError):
            payload = {}
        final_status = str(payload.get("status") or "")
        retryable_skip = (
            not explicit_target
            and final_status == "SKIPPED_EXTERNAL_UNAVAILABLE"
        )
        if result == 0 and not retryable_skip:
            return 0
        if attempt < max_attempts:
            print(
                f"[DIRECT_MEDIA_RETRY] candidate {attempt} unavailable; trying next approved parent",
                file=sys.stderr,
            )
    # External access can be transient. Exhausting the bounded candidate set
    # remains an observable fail-soft preparation result, never a publish pass.
    return 0 if final_status == "SKIPPED_EXTERNAL_UNAVAILABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
