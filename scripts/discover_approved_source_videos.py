#!/usr/bin/env python3
"""Discover video candidates from approved source channels/accounts.

This is a dry-run first planner. It does not download media, cut clips,
upload assets, post to Threads, or perform unbounded account scraping.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from itertools import islice
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import rights_allows_media_use  # noqa: E402
from acquisition.ytdlp_runtime import metadata_options  # noqa: E402
from media_growth_schemas import (  # noqa: E402
    SOURCE_VIDEO_FIELDS,
    build_source_video,
    canonicalize_video_url,
    extract_video_id,
    is_duplicate_source_video,
    redacted_preview,
)
from config_loader import get_config  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402
from reference.source_registry import load_registry  # noqa: E402
from source_discovery_policy import (  # noqa: E402
    build_state_update,
    plan_source_scan,
    select_unique_candidates,
)

SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"
CONFIG_FILE = ROOT / "config/media_growth_engine.json"
LOCAL_SOURCE_VIDEOS_FILE = ROOT / "output/source_videos/source_videos.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def load_sources() -> list[dict[str, Any]]:
    return load_registry()


def load_existing_source_videos(path: str = "") -> list[dict[str, Any]]:
    candidate = Path(path) if path else LOCAL_SOURCE_VIDEOS_FILE
    if not candidate.exists():
        return []
    return json.loads(candidate.read_text(encoding="utf-8"))


def _read_sheet_rows(
    client: SheetsClient,
    tab_name: str,
    operation: str,
) -> list[dict[str, Any]]:
    """Read an existing tab without creating it."""

    try:
        rows = client._call_with_rate_limit_retry(
            operation,
            lambda: client._ws(tab_name).get_all_records(),
        )
    except Exception as exc:
        if type(exc).__name__ == "WorksheetNotFound":
            return []

        raise

    return [dict(row) for row in rows]


def load_discovery_data_from_sheets(
    *,
    ensure_tabs: bool = False,
) -> tuple[
    SheetsClient,
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Read source videos and discovery state."""

    cfg = get_config()

    client = SheetsClient(
        cfg["sheet_id"],
        cfg["sa_dict"],
        dry_run=False,
    )

    if ensure_tabs:
        for tab_name in (
            "source_videos",
            "source_discovery_state",
        ):
            client._ensure_tab(
                tab_name,
                TAB_DEFINITIONS[tab_name],
            )

    videos = _read_sheet_rows(
        client,
        "source_videos",
        ("get_all_records:" "source_videos:discovery"),
    )

    state_rows = _read_sheet_rows(
        client,
        "source_discovery_state",
        ("get_all_records:" "source_discovery_state:" "discovery"),
    )

    return client, videos, state_rows


def load_existing_source_videos_from_sheets() -> tuple[
    SheetsClient,
    list[dict[str, Any]],
]:
    """Compatibility wrapper for existing callers."""

    client, videos, _ = load_discovery_data_from_sheets(ensure_tabs=False)

    return client, videos


def is_persistable_source_video(
    row: dict[str, Any],
) -> bool:
    """Allow only verified individual-video metadata into source_videos."""

    platform = str(row.get("platform", "")).lower()

    if platform not in {
        "youtube",
        "tiktok",
    }:
        return False

    if (
        str(
            row.get(
                "discovery_status",
                "",
            )
        )
        != "DISCOVERED"
    ):
        return False

    if not rights_allows_media_use(
        str(
            row.get(
                "rights_status",
                "",
            )
        )
    ):
        return False

    if (
        str(
            row.get(
                "permission_status",
                "",
            )
        )
        != "approved"
    ):
        return False

    if not str(
        row.get(
            "source_id",
            "",
        )
    ):
        return False

    if not str(
        row.get(
            "account_id",
            "",
        )
    ):
        return False

    title = str(row.get("title", "")).strip()
    if not title or "video candidate" in title.lower():
        return False

    original_url = str(
        row.get(
            "original_video_url",
            "",
        )
    )

    stored_canonical = str(
        row.get(
            "canonical_video_url",
            "",
        )
    )

    if not original_url or not stored_canonical:
        return False

    canonical_url = canonicalize_video_url(
        original_url,
        platform,
    )

    if canonical_url != canonicalize_video_url(
        stored_canonical,
        platform,
    ):
        return False

    video_id = extract_video_id(
        canonical_url,
        platform,
    )

    if not video_id:
        return False

    if video_id != str(
        row.get(
            "video_id",
            "",
        )
    ):
        return False

    if platform == "youtube":
        return len(video_id) == 11

    return video_id.isdigit()


def append_source_videos_to_sheets(
    client: SheetsClient,
    rows: list[dict[str, Any]],
) -> int:
    """Append only real, validated individual-video discovery rows."""

    if not rows:
        return 0

    invalid_ids = [
        str(
            row.get(
                "source_video_id",
                "",
            )
        )
        or f"row_{index}"
        for index, row in enumerate(
            rows,
            start=1,
        )
        if not is_persistable_source_video(row)
    ]

    if invalid_ids:
        raise ValueError("non_persistable_source_videos:" + ",".join(invalid_ids))

    ws = client._ws("source_videos")

    headers = client._call_with_rate_limit_retry(
        "row_values:source_videos:discovery",
        lambda: ws.row_values(1),
    )

    existing = [
        dict(row)
        for row in client._call_with_rate_limit_retry(
            "get_all_records:" "source_videos:" "discovery_append",
            lambda: ws.get_all_records(),
        )
    ]

    to_add = [
        row
        for row in rows
        if not is_duplicate_source_video(
            row,
            existing,
        )
    ]

    if not to_add:
        return 0

    client._call_with_rate_limit_retry(
        "append_rows:source_videos:discovery",
        lambda: ws.append_rows(
            [
                [
                    str(
                        row.get(
                            header,
                            "",
                        )
                    )
                    for header in headers
                ]
                for row in to_add
            ],
            value_input_option="USER_ENTERED",
        ),
    )

    return len(to_add)


def append_discovery_state_to_sheets(
    client: SheetsClient,
    rows: list[dict[str, Any]],
) -> int:
    """Append discovery-state snapshots idempotently."""

    if not rows:
        return 0

    client._ensure_tab(
        "source_discovery_state",
        TAB_DEFINITIONS["source_discovery_state"],
    )

    ws = client._ws("source_discovery_state")

    headers = client._call_with_rate_limit_retry(
        ("row_values:" "source_discovery_state:" "discovery"),
        lambda: ws.row_values(1),
    )

    existing = [
        dict(row)
        for row in client._call_with_rate_limit_retry(
            ("get_all_records:" "source_discovery_state:" "discovery_append"),
            lambda: ws.get_all_records(),
        )
    ]

    existing_keys = {
        (
            str(
                row.get(
                    "state_id",
                    "",
                )
            ),
            str(
                row.get(
                    "last_scan_at",
                    "",
                )
            ),
            str(
                row.get(
                    "updated_at",
                    "",
                )
            ),
        )
        for row in existing
    }

    to_add = [
        row
        for row in rows
        if (
            str(
                row.get(
                    "state_id",
                    "",
                )
            ),
            str(
                row.get(
                    "last_scan_at",
                    "",
                )
            ),
            str(
                row.get(
                    "updated_at",
                    "",
                )
            ),
        )
        not in existing_keys
    ]

    if not to_add:
        return 0

    client._call_with_rate_limit_retry(
        ("append_rows:" "source_discovery_state:" "discovery"),
        lambda: ws.append_rows(
            [
                [
                    str(
                        row.get(
                            header,
                            "",
                        )
                    )
                    for header in headers
                ]
                for row in to_add
            ],
            value_input_option=("USER_ENTERED"),
        ),
    )

    return len(to_add)


def permission_ok(source: dict[str, Any]) -> bool:
    evidence_type = str(source.get("permission_evidence_type", ""))
    if source.get("registered_owner_scope_id"):
        return (
            source.get("permission_status") == "approved"
            and evidence_type == "owner_attestation"
            and bool(source.get("permission_evidence_reference"))
            and bool(source.get("permission_approved_by"))
            and bool(source.get("provenance_required"))
            and bool(source.get("original_author_match_required"))
        )
    return (
        source.get("permission_status") == "approved"
        and bool(evidence_type)
        and bool(source.get("permission_evidence_note"))
        and bool(source.get("permission_approved_by"))
    )


def select_discovery_sources(account_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    allowed_ids = set(config.get("allowed_source_ids", []))
    allowed_types = set(config.get("allowed_source_types_for_discovery", ["channel", "account"]))
    rows = []
    for source in load_sources():
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        active = source.get("active") is True or str(source.get("active", "")).lower() == "true"
        if not active:
            continue
        if account_id != "all" and account_id not in targets:
            continue
        if not source.get("registered_owner_scope_id") and source.get("source_id") not in allowed_ids:
            continue
        if source.get("source_type") not in allowed_types:
            continue
        if config.get("require_source_media_autopilot_enabled") and not source.get(
            "media_autopilot_enabled"
        ):
            continue
        rows.append(source)
    return rows


def order_sources_for_discovery(
    sources: list[dict[str, Any]],
    existing_source_videos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Give sources with less accumulated inventory the next bounded turn."""
    counts: dict[str, int] = {}
    latest: dict[str, str] = {}
    for row in existing_source_videos:
        source_id = str(row.get("source_id", ""))
        counts[source_id] = counts.get(source_id, 0) + 1
        latest[source_id] = max(
            latest.get(source_id, ""),
            str(row.get("last_seen_at") or row.get("discovered_at") or ""),
        )
    return sorted(
        sources,
        key=lambda source: (
            counts.get(str(source.get("source_id", "")), 0),
            latest.get(str(source.get("source_id", "")), ""),
            str(source.get("source_id", "")),
        ),
    )


def build_source_video_candidates(
    source: dict[str, Any],
    config: dict[str, Any],
    scan_plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build bounded dry-run candidates for one scan range."""

    if scan_plan is None:
        scan_plan = {
            "mode": "initial",
            "start_position": 1,
            "scan_limit": int(
                config.get(
                    "max_videos_per_source_scan",
                    50,
                )
            ),
        }

    start_position = max(
        1,
        int(
            scan_plan.get(
                "start_position",
                1,
            )
        ),
    )

    scan_limit = max(
        1,
        int(
            scan_plan.get(
                "scan_limit",
                config.get(
                    "max_videos_per_source_scan",
                    50,
                ),
            )
        ),
    )

    rows = []

    for position in range(
        start_position,
        start_position + scan_limit,
    ):
        row = build_source_video(
            source,
            index=position,
            discovery_status="PLANNED_ONLY",
        )

        row["source_position"] = position
        row["discovery_mode"] = str(
            scan_plan.get(
                "mode",
                "initial",
            )
        )

        rows.append(row)

    return rows


def _entry_video_url(source: dict[str, Any], entry: dict[str, Any]) -> str:
    platform = str(source.get("source_platform", ""))
    raw = str(entry.get("webpage_url") or entry.get("url") or "")
    video_id = str(entry.get("id") or "")
    if platform == "youtube" and video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    if platform == "tiktok" and video_id:
        handle = str(source.get("source_handle") or source.get("handle") or "").lstrip("@")
        if not handle:
            match = re.search(r"tiktok\.com/@([^/?]+)", str(source.get("source_url", "")))
            handle = match.group(1) if match else ""
        if handle:
            return f"https://www.tiktok.com/@{handle}/video/{video_id}"
    return raw


def merge_video_detail_metadata(
    row: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Merge verified per-video metadata without changing source identity."""
    updated = dict(row)
    title = str(entry.get("title") or "").strip()
    if title:
        updated["title"] = title
    description = str(entry.get("description") or "").strip()
    if description:
        updated["description_preview"] = redacted_preview(description)
    duration = entry.get("duration")
    if duration not in (None, ""):
        updated["duration_seconds"] = duration
    updated["author_handle"] = str(
        entry.get("uploader_id")
        or entry.get("channel_id")
        or updated.get("author_handle")
        or ""
    )
    updated["published_at"] = str(
        entry.get("upload_date")
        or entry.get("timestamp")
        or updated.get("published_at")
        or ""
    )
    for field in ("view_count", "like_count", "comment_count"):
        if entry.get(field) not in (None, ""):
            updated[field] = entry[field]
    updated["collection_backend"] = "yt_dlp_flat_then_bounded_video_detail"
    return updated


def enrich_selected_video_metadata(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fetch detail only for the already bounded, deduplicated candidates."""
    if not rows or importlib.util.find_spec("yt_dlp") is None:
        return [dict(row) for row in rows]
    import yt_dlp  # type: ignore[import]

    enriched: list[dict[str, Any]] = []
    for row in rows:
        platform = str(row.get("platform", "")).lower()
        video_url = str(row.get("canonical_video_url") or "")
        if platform not in {"youtube", "tiktok"} or not video_url:
            enriched.append(dict(row))
            continue
        try:
            with yt_dlp.YoutubeDL(metadata_options(platform, {
                "skip_download": True,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "socket_timeout": 20,
                "retries": 1,
            })) as ydl:
                entry = ydl.extract_info(video_url, download=False) or {}
        except Exception:
            entry = {}
        enriched.append(
            merge_video_detail_metadata(row, entry)
            if isinstance(entry, dict) and str(entry.get("title") or "").strip()
            else dict(row)
        )
    return enriched


def _bounded_public_comments(
    platform: str,
    video_url: str,
    metadata: dict[str, Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Read comments only from bounded public providers, never fabricate them."""
    bounded = max(0, min(int(limit), 20))
    if platform == "youtube":
        try:
            from youtube_comment_downloader import SORT_BY_POPULAR, YoutubeCommentDownloader

            raw = YoutubeCommentDownloader().get_comments_from_url(
                video_url, sort_by=SORT_BY_POPULAR
            )
            rows = []
            for item in islice(raw, bounded):
                text = str(item.get("text", "")).strip()
                if text:
                    rows.append({"text": text[:1000], "like_count": item.get("votes", "")})
            return rows
        except Exception:  # Optional ranking evidence must not block discovery.
            return []
    raw_comments = metadata.get("comments")
    if platform == "tiktok" and isinstance(raw_comments, list):
        rows = []
        for item in raw_comments[:bounded]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("content") or "").strip()
            if text:
                rows.append({"text": text[:1000], "like_count": item.get("like_count", "")})
        return rows
    return []


YOUTUBE_PUBLIC_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')


def _assigned_json_object(html: str, marker: str) -> dict[str, Any] | None:
    """Parse one bounded JSON assignment without evaluating page JavaScript."""
    marker_index = html.find(marker)
    if marker_index < 0:
        return None
    start = html.find("{", marker_index + len(marker))
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(html)):
        char = html[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    value = json.loads(html[start:index + 1])
                except json.JSONDecodeError:
                    return None
                return value if isinstance(value, dict) else None
    return None


def _youtube_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    if str(value.get("simpleText") or "").strip():
        return str(value["simpleText"]).strip()
    runs = value.get("runs")
    if isinstance(runs, list):
        return "".join(
            str(item.get("text") or "")
            for item in runs
            if isinstance(item, dict)
        ).strip()
    return ""


def _youtube_duration_seconds(value: Any) -> int:
    text = _youtube_text(value)
    if not re.fullmatch(r"\d{1,3}(?::\d{1,2}){1,2}", text):
        return 0
    total = 0
    for part in text.split(":"):
        total = total * 60 + int(part)
    return total


def youtube_public_video_entries(html: str) -> list[dict[str, Any]]:
    """Read real video metadata embedded in a public channel's ytInitialData."""
    initial_data = None
    for marker in ("var ytInitialData =", "window[\"ytInitialData\"] =", "ytInitialData ="):
        initial_data = _assigned_json_object(html, marker)
        if initial_data is not None:
            break
    if initial_data is None:
        return []

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    stack: list[Any] = [initial_data]
    while stack:
        value = stack.pop()
        if isinstance(value, list):
            stack.extend(reversed(value))
            continue
        if not isinstance(value, dict):
            continue
        video_id = str(value.get("videoId") or "")
        title = _youtube_text(value.get("title"))
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) and title and video_id not in seen:
            seen.add(video_id)
            entries.append({
                "id": video_id,
                "title": title,
                "duration": _youtube_duration_seconds(value.get("lengthText")),
                "description": _youtube_text(value.get("descriptionSnippet")),
                "published_at": _youtube_text(value.get("publishedTimeText")),
            })
        stack.extend(reversed(list(value.values())))
    return entries


def youtube_public_video_ids(
    html: str,
    *,
    limit: int,
    start_position: int = 1,
) -> list[str]:
    """Return unique IDs from a public YouTube channel page within its cap."""
    ids: list[str] = []
    seen: set[str] = set()
    start = max(1, start_position)
    for video_id in YOUTUBE_PUBLIC_VIDEO_ID_RE.findall(html):
        if video_id in seen:
            continue
        seen.add(video_id)
        ids.append(video_id)
        if len(ids) >= start - 1 + max(1, limit):
            break
    return ids[start - 1:]


def discover_youtube_public_html(
    source: dict[str, Any],
    config: dict[str, Any],
    scan_plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Bounded unauthenticated fallback when flat channel extraction is empty."""
    source_url = str(source.get("source_url", "")).rstrip("/")
    if not source_url:
        return [], "youtube_public_html_source_url_missing"
    limit = max(1, int(scan_plan.get("scan_limit", config.get("max_videos_per_source_scan", 12))))
    try:
        request = Request(
            f"{source_url}/videos",
            headers={"User-Agent": "Mozilla/5.0 (compatible; SNSGrowthEngine/1.0)"},
        )
        with urlopen(request, timeout=20) as response:  # nosec B310: approved public source only
            html = response.read(2_000_000).decode("utf-8", errors="replace")
    except Exception as exc:
        return [], f"youtube_public_html_failed:{type(exc).__name__}"
    # The page scan may inspect a bounded range, but detail enrichment is
    # capped to the number this run can actually admit.
    detail_limit = min(
        limit,
        max(1, int(scan_plan.get("per_source_new_limit", config.get("max_new_videos_per_source_per_run", 3)))),
    )
    start_position = int(scan_plan.get("start_position", 1))
    structured_entries = youtube_public_video_entries(html)
    selected_entries = structured_entries[
        max(0, start_position - 1):max(0, start_position - 1) + detail_limit
    ]
    video_ids = [str(entry["id"]) for entry in selected_entries]
    if not video_ids:
        video_ids = youtube_public_video_ids(
            html,
            limit=detail_limit,
            start_position=start_position,
        )
        selected_entries = [{"id": video_id} for video_id in video_ids]
    if not video_ids:
        return [], "youtube_public_html_no_individual_videos"
    yt_dlp_available = importlib.util.find_spec("yt_dlp") is not None
    if yt_dlp_available:
        import yt_dlp  # type: ignore[import]

    rows: list[dict[str, Any]] = []
    for position, public_entry in enumerate(selected_entries, start=start_position):
        video_id = str(public_entry["id"])
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        entry = dict(public_entry)
        detail_used = False
        if yt_dlp_available:
            try:
                with yt_dlp.YoutubeDL(metadata_options("youtube", {
                    "skip_download": True,
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                    "ignoreerrors": True,
                    "socket_timeout": 20,
                })) as ydl:
                    detail = ydl.extract_info(video_url, download=False) or {}
            except Exception:
                detail = {}
            if isinstance(detail, dict):
                verified_detail = {key: value for key, value in detail.items() if value not in (None, "")}
                detail_used = bool(str(verified_detail.get("title") or "").strip())
                entry = {**entry, **verified_detail}
        row = build_source_video(
            source,
            index=position,
            video_url=video_url,
            title=str(entry.get("title") or ""),
            duration_seconds=entry.get("duration") or 0,
            description=str(entry.get("description") or ""),
            discovery_status="DISCOVERED",
        )
        row["source_position"] = position
        row["discovery_mode"] = str(scan_plan.get("mode", "initial"))
        row["collection_backend"] = (
            "youtube_public_html_structured_then_ytdlp_metadata"
            if detail_used
            else "youtube_public_html_structured"
            if str(public_entry.get("title") or "").strip()
            else "youtube_public_html_video_id_only"
        )
        row["author_handle"] = str(entry.get("uploader_id") or entry.get("channel_id") or source.get("source_handle") or "")
        row["published_at"] = str(entry.get("upload_date") or entry.get("timestamp") or entry.get("published_at") or "")
        row["view_count"] = entry.get("view_count") or ""
        row["like_count"] = entry.get("like_count") or ""
        row["comment_count"] = entry.get("comment_count") or ""
        rows.append(row)
    return rows, "YOUTUBE_PUBLIC_HTML_FALLBACK"


def discover_source_videos_real(
    source: dict[str, Any],
    config: dict[str, Any],
    scan_plan: dict[str, Any] | None = None,
) -> tuple[
    list[dict[str, Any]],
    str,
]:
    """Discover one bounded account range without downloading media."""

    if importlib.util.find_spec("yt_dlp") is None:
        return [], "yt_dlp_not_installed"

    import yt_dlp  # type: ignore[import]

    if scan_plan is None:
        scan_plan = {
            "mode": "initial",
            "start_position": 1,
            "scan_limit": int(
                config.get(
                    "max_videos_per_source_scan",
                    50,
                )
            ),
        }

    start_position = max(
        1,
        int(
            scan_plan.get(
                "start_position",
                1,
            )
        ),
    )

    scan_limit = max(
        1,
        int(
            scan_plan.get(
                "scan_limit",
                config.get(
                    "max_videos_per_source_scan",
                    50,
                ),
            )
        ),
    )

    end_position = start_position + scan_limit - 1

    platform = str(
        source.get(
            "source_platform",
            "",
        )
    ).lower()

    opts = metadata_options(
        platform,
        {
            "extract_flat": "in_playlist",
            "playliststart": start_position,
            "playlistend": end_position,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "socket_timeout": 20,
        },
    )

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                str(
                    source.get(
                        "source_url",
                        "",
                    )
                ),
                download=False,
            )
    except Exception as exc:
        if platform == "youtube":
            return discover_youtube_public_html(source, config, scan_plan)
        return (
            [],
            f"{type(exc).__name__}: " "discovery_failed",
        )

    if not info:
        if platform == "youtube":
            return discover_youtube_public_html(source, config, scan_plan)
        return [], "metadata_unavailable"

    entries = info.get("entries") if isinstance(info, dict) else None

    if entries is None:
        entries = [info]

    rows: list[dict[str, Any]] = []

    valid_entries = (entry for entry in entries if isinstance(entry, dict))

    for fallback_position, entry in enumerate(
        valid_entries,
        start=start_position,
    ):
        if len(rows) >= scan_limit:
            break

        try:
            source_position = int(
                entry.get(
                    "playlist_index",
                    fallback_position,
                )
            )
        except (TypeError, ValueError):
            source_position = fallback_position

        video_url = _entry_video_url(
            source,
            entry,
        )

        video_id = extract_video_id(
            video_url,
            platform,
        )

        if not video_url or not video_id:
            continue

        if platform == "youtube" and len(video_id) != 11:
            continue

        if platform == "tiktok" and not video_id.isdigit():
            continue

        # Discovery deliberately uses flat metadata only.
        # Per-video detail retrieval is deferred until the
        # candidate survives dedupe and is processed later.
        row = build_source_video(
            source,
            index=source_position,
            video_url=video_url,
            title=str(entry.get("title") or ""),
            duration_seconds=(entry.get("duration") or 0),
            description=str(entry.get("description") or ""),
            discovery_status="DISCOVERED",
        )

        row["source_position"] = source_position

        row["discovery_mode"] = str(
            scan_plan.get(
                "mode",
                "initial",
            )
        )

        row["author_handle"] = str(
            entry.get("uploader_id") or entry.get("channel_id") or source.get("source_handle") or ""
        )

        row["published_at"] = str(entry.get("upload_date") or entry.get("timestamp") or "")

        row["view_count"] = entry.get("view_count") or ""

        row["like_count"] = entry.get("like_count") or ""

        row["comment_count"] = entry.get("comment_count") or ""

        raw_comments = entry.get("comments") if platform == "tiktok" else []

        comments = (
            _bounded_public_comments(
                platform,
                video_url,
                {
                    "comments": raw_comments,
                },
                limit=20,
            )
            if raw_comments
            else []
        )

        row["comments_json"] = json.dumps(
            comments,
            ensure_ascii=False,
        )

        row["comment_count_collected"] = str(len(comments))

        rows.append(row)

    if not rows and platform == "youtube":
        return discover_youtube_public_html(source, config, scan_plan)
    return rows, "REAL_DISCOVERY" if rows else "NO_INDIVIDUAL_VIDEOS"


def _source_discovery_status(source: dict[str, Any]) -> str:
    platform = source.get("source_platform")
    if platform == "youtube":
        return "YOUTUBE_CHANNEL_DISCOVERY_PLAN"
    if platform == "tiktok":
        return "TIKTOK_ACCOUNT_LIMITED_MANUAL_SAFE_PLAN"
    return "DISCOVERY_PLAN"


def build_discovery_plan(
    account_id: str,
    *,
    apply: bool = False,
    confirm_discovery: bool = False,
    existing_source_videos: list[dict[str, Any]] | None = None,
    discovery_state_rows: list[dict[str, Any]] | None = None,
    fetch_real: bool = False,
    source_ids: list[str] | None = None,
    start_position: int | None = None,
) -> dict[str, Any]:
    config = load_config()

    existing = (
        existing_source_videos
        if existing_source_videos is not None
        else load_existing_source_videos()
    )

    state_rows = discovery_state_rows if discovery_state_rows is not None else []

    selected_sources = order_sources_for_discovery(
        select_discovery_sources(
            account_id,
            config,
        ),
        existing,
    )

    # Operators may validate one approved channel at a time before enabling a
    # broader bounded scan. Unknown IDs intentionally select nothing rather
    # than widening the operation.
    requested_source_ids = {str(source_id) for source_id in (source_ids or []) if str(source_id)}
    if requested_source_ids:
        selected_sources = [
            source for source in selected_sources
            if str(source.get("source_id", "")) in requested_source_ids
        ]

    blocked: list[str] = []

    if not config.get("source_video_discovery_enabled"):
        blocked.append("source_video_discovery_disabled")

    if apply and not confirm_discovery:
        blocked.append("--apply requires " "--confirm-discovery")
    if apply and not fetch_real:
        blocked.append("--apply requires --fetch-real")

    if apply and not config.get("source_video_discovery_apply_enabled"):
        blocked.append("source_video_discovery_apply_disabled")

    max_total = int(
        config.get(
            "max_total_new_videos_per_run",
            20,
        )
    )

    source_results = []
    new_videos: list[dict[str, Any]] = []
    state_updates: list[dict[str, Any]] = []

    duplicate_count = 0
    skipped_count = 0
    scanned_count = 0

    for source in selected_sources:
        source_blocked: list[str] = []

        source_id = str(
            source.get(
                "source_id",
                "",
            )
        )

        platform = str(
            source.get(
                "source_platform",
                "",
            )
        )

        rights = str(
            source.get(
                "rights_status",
                "",
            )
        )

        if not rights_allows_media_use(rights):
            source_blocked.append("rights_status_not_media_approved")

        if not permission_ok(source):
            source_blocked.append("permission_evidence_missing")

        targets = source.get("target_account_ids") or [source.get("target_account_id")]

        target_account_id = str(
            next(
                (target for target in targets if target),
                (account_id if account_id != "all" else ""),
            )
        )

        scan_plan = plan_source_scan(
            source_id=source_id,
            account_id=target_account_id,
            item_type="video",
            existing_rows=existing,
            state_rows=state_rows,
            config=config,
        )
        if start_position is not None:
            scan_plan = {
                **scan_plan,
                "mode": "operator_bounded_window",
                "start_position": max(1, int(start_position)),
            }

        discovery_status = _source_discovery_status(source)

        if len(new_videos) >= max_total:
            source_results.append(
                {
                    "source_id": source_id,
                    "account_id": target_account_id,
                    "platform": platform,
                    "source_type": source.get("source_type"),
                    "source_url": (
                        canonicalize_video_url(
                            source.get(
                                "source_url",
                                "",
                            ),
                            platform,
                        )
                    ),
                    "rights_status": rights,
                    "permission_status": (
                        source.get(
                            "permission_status",
                            "",
                        )
                    ),
                    "discovery_status": ("MAX_TOTAL_LIMIT_REACHED"),
                    "scan_mode": (scan_plan["mode"]),
                    "start_position": (scan_plan["start_position"]),
                    "scan_limit": (scan_plan["scan_limit"]),
                    "inventory_count": (scan_plan["inventory_count"]),
                    "inventory_target": (scan_plan["inventory_target"]),
                    "new_limit": (scan_plan["per_source_new_limit"]),
                    "adapter_candidate_count": 0,
                    "discovered_video_count": 0,
                    "new_video_count": 0,
                    "duplicate_video_count": 0,
                    "max_duplicate_streak": 0,
                    "stop_reason": ("max_total_new_reached"),
                    "state_update_planned": False,
                    "blocked_reasons": [],
                }
            )

            skipped_count += 1
            continue

        if source_blocked:
            candidates = []
        elif fetch_real:
            (
                candidates,
                discovery_status,
            ) = discover_source_videos_real(
                source,
                config,
                scan_plan,
            )
        else:
            candidates = build_source_video_candidates(
                source,
                config,
                scan_plan,
            )

        if source_blocked:
            selection = {
                "selected": [],
                "new_count": 0,
                "duplicate_count": 0,
                "scanned_count": 0,
                "max_duplicate_streak": 0,
                "max_scanned_position": (int(scan_plan["start_position"]) - 1),
                "stop_reason": ("source_blocked"),
            }
        else:
            selection = select_unique_candidates(
                candidates=candidates,
                existing_rows=existing,
                selected_this_run=(new_videos),
                duplicate_checker=(is_duplicate_source_video),
                scan_plan=scan_plan,
            )

        selected_rows = list(
            selection.get(
                "selected",
                [],
            )
        )

        detail_candidates = selected_rows
        if fetch_real and selected_rows:
            selected_rows = [
                row
                for row in enrich_selected_video_metadata(selected_rows)
                if is_persistable_source_video(row)
            ]
            selection["selected"] = selected_rows
            selection["new_count"] = len(selected_rows)
            if detail_candidates and not selected_rows:
                selection["stop_reason"] = "video_detail_metadata_unavailable"

        new_videos.extend(selected_rows)

        source_duplicates = int(
            selection.get(
                "duplicate_count",
                0,
            )
        )

        source_scanned = int(
            selection.get(
                "scanned_count",
                0,
            )
        )

        duplicate_count += source_duplicates

        scanned_count += source_scanned

        skipped_count += max(
            0,
            len(candidates) - source_scanned,
        )

        scan_completed = not source_blocked and not (
            detail_candidates and not selected_rows
        ) and (
            not fetch_real
            or discovery_status
            in {
                "REAL_DISCOVERY",
                "NO_INDIVIDUAL_VIDEOS",
            }
        )

        state_update = {}

        if scan_completed:
            latest_candidate = {}

            if (
                scan_plan["mode"]
                in {
                    "initial",
                    "incremental",
                }
                and candidates
            ):
                latest_candidate = candidates[0]

            state_update = build_state_update(
                scan_plan=scan_plan,
                selection=selection,
                latest_seen_item_id=str(
                    latest_candidate.get(
                        "video_id",
                        "",
                    )
                ),
                latest_seen_published_at=str(
                    latest_candidate.get(
                        "published_at",
                        "",
                    )
                ),
                platform=platform,
            )

            state_updates.append(state_update)

        source_results.append(
            {
                "source_id": source_id,
                "account_id": target_account_id,
                "platform": platform,
                "source_type": source.get("source_type"),
                "source_url": (
                    canonicalize_video_url(
                        source.get(
                            "source_url",
                            "",
                        ),
                        platform,
                    )
                ),
                "rights_status": rights,
                "permission_status": (
                    source.get(
                        "permission_status",
                        "",
                    )
                ),
                "discovery_status": (discovery_status),
                "scan_mode": (scan_plan["mode"]),
                "start_position": (scan_plan["start_position"]),
                "scan_limit": (scan_plan["scan_limit"]),
                "inventory_count": (scan_plan["inventory_count"]),
                "inventory_target": (scan_plan["inventory_target"]),
                "new_limit": (scan_plan["per_source_new_limit"]),
                "adapter_candidate_count": (len(candidates)),
                "discovered_video_count": (source_scanned),
                "new_video_count": (len(selected_rows)),
                "duplicate_video_count": (source_duplicates),
                "max_duplicate_streak": (
                    selection.get(
                        "max_duplicate_streak",
                        0,
                    )
                ),
                "stop_reason": (
                    selection.get(
                        "stop_reason",
                        "",
                    )
                ),
                "state_update_planned": (bool(state_update)),
                "blocked_reasons": (source_blocked),
            }
        )

    plan = {
        "status": ("BLOCKED" if blocked else "PLAN_ONLY"),
        "account_id": account_id,
        "selected_sources": [
            {
                "source_id": source.get("source_id"),
                "platform": source.get("source_platform"),
                "source_type": source.get("source_type"),
            }
            for source in selected_sources
        ],
        "requested_source_ids": sorted(requested_source_ids),
        "requested_start_position": start_position,
        "discovery_enabled": bool(config.get("source_video_discovery_enabled")),
        "source_video_discovery_apply_enabled": (
            bool(config.get("source_video_discovery_apply_enabled"))
        ),
        "source_discovery_state_enabled": (bool(config.get("source_discovery_state_enabled"))),
        "limits": {
            "initial_source_scan_limit": int(
                config.get(
                    "initial_source_scan_limit",
                    30,
                )
            ),
            "incremental_source_scan_limit": int(
                config.get(
                    "incremental_source_scan_limit",
                    12,
                )
            ),
            "backfill_source_scan_limit": int(
                config.get(
                    "backfill_source_scan_limit",
                    30,
                )
            ),
            "consecutive_existing_stop": int(
                config.get(
                    "consecutive_existing_stop",
                    5,
                )
            ),
            "max_new_videos_per_source_per_run": (
                int(
                    config.get(
                        "max_new_videos_per_source_per_run",
                        10,
                    )
                )
            ),
            "max_total_new_videos_per_run": (max_total),
        },
        "dedupe_keys": config.get(
            "dedupe_keys",
            [],
        ),
        "source_videos_schema": (SOURCE_VIDEO_FIELDS),
        "discovery_state_schema": (TAB_DEFINITIONS["source_discovery_state"]),
        "adapter_status": {
            "yt_dlp": ("installed" if importlib.util.find_spec("yt_dlp") else "not_installed"),
            "network_fetch": ("invoked_bounded" if fetch_real else "not_invoked"),
            "tiktok_account_expansion": ("limited_manual_safe"),
        },
        "source_results": source_results,
        "discovered_video_count": (scanned_count),
        "new_video_count": (len(new_videos)),
        "duplicate_video_count": (duplicate_count),
        "skipped_video_count": (skipped_count),
        "new_videos": new_videos,
        "new_videos_preview": (new_videos[:5]),
        "discovery_state_updates": (state_updates),
        "would_save_source_videos": (
            bool(apply and confirm_discovery and not blocked and new_videos)
        ),
        "would_save_discovery_state": (
            bool(
                apply
                and confirm_discovery
                and not blocked
                and config.get("source_discovery_state_enabled")
                and state_updates
            )
        ),
        "blocked_reasons": blocked,
        "fetch_real": fetch_real,
    }

    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=("discover approved source videos"))

    parser.add_argument(
        "--account-id",
        default="liver_manager",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--confirm-discovery",
        action="store_true",
    )

    parser.add_argument(
        "--existing-source-videos-json",
        default="",
    )

    parser.add_argument(
        "--use-sheets",
        action="store_true",
        help=("read inventory and cursor state; " "write only with explicit apply"),
    )

    parser.add_argument(
        "--fetch-real",
        action="store_true",
        help=("bounded metadata discovery; " "never downloads media"),
    )

    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help=("limit bounded discovery to an approved source ID; repeatable"),
    )

    parser.add_argument(
        "--start-position",
        type=int,
        default=None,
        help=("start an approved source scan at this one-based position"),
    )

    args = parser.parse_args()

    client = None
    existing = None
    state_rows = None

    if args.use_sheets:
        (
            client,
            existing,
            state_rows,
        ) = load_discovery_data_from_sheets(ensure_tabs=(args.apply and args.confirm_discovery))

    elif args.existing_source_videos_json:
        existing = load_existing_source_videos(args.existing_source_videos_json)

    plan = build_discovery_plan(
        args.account_id,
        apply=args.apply,
        confirm_discovery=(args.confirm_discovery),
        existing_source_videos=existing,
        discovery_state_rows=state_rows,
        fetch_real=args.fetch_real,
        source_ids=args.source_id,
        start_position=args.start_position,
    )

    if (
        args.apply
        and args.confirm_discovery
        and args.use_sheets
        and client
        and plan["status"] != "BLOCKED"
    ):
        added = append_source_videos_to_sheets(
            client,
            plan.get(
                "new_videos",
                [],
            ),
        )

        state_added = 0

        if plan.get("source_discovery_state_enabled"):
            state_added = append_discovery_state_to_sheets(
                client,
                plan.get(
                    "discovery_state_updates",
                    [],
                ),
            )

        plan["saved_source_video_count"] = added

        plan["saved_discovery_state_count"] = state_added

        plan["would_save_source_videos"] = False

        plan["would_save_discovery_state"] = False

        plan["source_videos_save_status"] = "SAVED" if added else "NO_NEW_ROWS"

        plan["discovery_state_save_status"] = "SAVED" if state_added else "NO_NEW_STATE"

    elif (
        args.apply
        and args.confirm_discovery
        and not args.use_sheets
        and plan["status"] != "BLOCKED"
    ):
        plan["source_videos_save_status"] = "SKIPPED_USE_SHEETS_REQUIRED"

        plan["discovery_state_save_status"] = "SKIPPED_USE_SHEETS_REQUIRED"

    print(
        json.dumps(
            plan,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 1 if (plan["status"] == "BLOCKED" and args.apply) else 0


if __name__ == "__main__":
    raise SystemExit(main())
