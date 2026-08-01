#!/usr/bin/env python3
"""Prioritize reliable, recent direct-media candidates."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import ingest_direct_reference_media as core


_PLATFORM_PRIORITY = {
    "threads": 0,
    "tiktok": 1,
    "youtube": 2,
}


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

    pending: list[tuple[int, str, str]] = []

    for media in client._ws(
        "source_post_media"
    ).get_all_records():
        post = posts.get(
            str(
                media.get(
                    "source_post_id",
                    "",
                )
            )
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
        ):
            continue

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
        ):
            continue

        download_status = str(
            media.get(
                "download_status",
                "",
            )
        ).upper()

        if download_status in {
            "FAILED",
            "BLOCKED",
            "SKIPPED_EXTERNAL_UNAVAILABLE",
        }:
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

        if platform == "youtube":
            if (
                "/watch" not in url
                and "/shorts/" not in url
            ):
                continue

        elif platform == "tiktok":
            if "/video/" not in url:
                continue

        elif platform == "threads":
            if not core.safe_https_url(
                url,
                stream_url=True,
            ):
                continue

            if _looks_like_threads_placeholder(url):
                continue

        else:
            continue

        media_id = str(
            media.get(
                "source_post_media_id",
                "",
            )
        )

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


core.select_pending_media_id = select_pending_media_id


if __name__ == "__main__":
    raise SystemExit(core.main())
