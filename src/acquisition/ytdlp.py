"""yt-dlp PRIMARY adapter for public YouTube/TikTok profile discovery."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.request import Request, urlopen

from .contracts import ProviderResult
from .models import (
    NormalizedMediaItem,
    NormalizedSourcePost,
    canonical_url,
    external_post_id,
    stable_content_hash,
    utc_now,
)
from .router import BackendFailure
from .ytdlp_runtime import metadata_options


YOUTUBE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_VIDEO_ID_IN_HTML = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')


def _assigned_json_object(html: str, marker: str) -> dict[str, Any] | None:
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


def _youtube_lockup_title(value: dict[str, Any]) -> str:
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    lockup = metadata.get("lockupMetadataViewModel")
    if not isinstance(lockup, dict):
        return ""
    title = lockup.get("title")
    if not isinstance(title, dict):
        return ""
    return str(title.get("content") or "").strip()


def youtube_public_entries(html: str) -> list[dict[str, Any]]:
    """Extract real individual videos from public server-rendered channel data."""
    initial_data = None
    for marker in (
        "var ytInitialData =",
        'window["ytInitialData"] =',
        "ytInitialData =",
    ):
        initial_data = _assigned_json_object(html, marker)
        if initial_data is not None:
            break

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    if initial_data is not None:
        stack: list[Any] = [initial_data]
        while stack:
            value = stack.pop()
            if isinstance(value, list):
                stack.extend(reversed(value))
                continue
            if not isinstance(value, dict):
                continue
            video_id = str(value.get("videoId") or value.get("contentId") or "")
            title = _youtube_text(value.get("title")) or _youtube_lockup_title(value)
            if YOUTUBE_VIDEO_ID.fullmatch(video_id) and title and video_id not in seen:
                seen.add(video_id)
                rows.append(
                    {
                        "id": video_id,
                        "url": video_id,
                        "title": title,
                        "description": _youtube_text(value.get("descriptionSnippet")),
                        "duration": _youtube_duration_seconds(value.get("lengthText")),
                        "published_at": _youtube_text(value.get("publishedTimeText")),
                    }
                )
            stack.extend(reversed(list(value.values())))

    if rows:
        return rows

    for video_id in YOUTUBE_VIDEO_ID_IN_HTML.findall(html):
        if video_id in seen:
            continue
        seen.add(video_id)
        rows.append({"id": video_id, "url": video_id})
    return rows


def discover_youtube_public_entries(
    source_url: str,
    *,
    start_position: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Read a bounded, stable union of public Videos and Shorts tabs."""
    base_url = str(source_url or "").rstrip("/")
    for suffix in ("/videos", "/shorts", "/streams"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
            break

    tab_rows: list[list[dict[str, Any]]] = []
    for tab in ("videos", "shorts"):
        try:
            request = Request(
                f"{base_url}/{tab}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; SNSGrowthEngine/1.0)"},
            )
            with urlopen(request, timeout=20) as response:  # nosec B310: approved public source only
                html = response.read(2_000_000).decode("utf-8", errors="replace")
        except Exception:
            tab_rows.append([])
            continue
        tab_rows.append(youtube_public_entries(html)[: max(1, limit)])

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    max_length = max((len(rows) for rows in tab_rows), default=0)
    for index in range(max_length):
        for rows in tab_rows:
            if index >= len(rows):
                continue
            row = rows[index]
            video_id = str(row.get("id") or "")
            if not YOUTUBE_VIDEO_ID.fullmatch(video_id) or video_id in seen:
                continue
            seen.add(video_id)
            merged.append(row)

    start = max(0, int(start_position) - 1)
    return merged[start:start + max(1, int(limit))]


def _individual_entry_url(platform: str, entry: dict[str, Any]) -> str:
    raw_url = str(entry.get("webpage_url") or entry.get("url") or "").strip()
    if platform == "youtube" and YOUTUBE_VIDEO_ID.fullmatch(raw_url):
        return f"https://www.youtube.com/watch?v={raw_url}"
    return raw_url


def _is_individual_youtube_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    raw_url = _individual_entry_url("youtube", entry)
    return bool(
        YOUTUBE_VIDEO_ID.fullmatch(str(entry.get("id") or ""))
        and (
            YOUTUBE_VIDEO_ID.fullmatch(raw_url)
            or "/watch" in raw_url
            or "/shorts/" in raw_url
        )
    )


def _source_author_handle(source: dict[str, Any], entry: dict[str, Any]) -> str:
    """Keep the bounded profile identity instead of comparing handle to channel ID."""
    entry_handle = str(entry.get("uploader_id") or "").strip()
    if entry_handle.startswith("@"):
        return entry_handle
    return str(source.get("source_handle") or source.get("author_handle") or entry_handle).strip()


class YtDlpProfilePostAdapter:
    backend_name = "yt_dlp"
    backend_version = "python-module"

    def acquire(
        self,
        source: dict[str, Any],
        *,
        limit: int,
    ) -> list[NormalizedSourcePost]:
        try:
            import yt_dlp
        except ImportError as exc:
            raise BackendFailure("yt_dlp_not_installed") from exc

        platform = str(source.get("source_platform") or source.get("platform") or "").lower()

        if platform not in {
            "youtube",
            "tiktok",
        }:
            raise BackendFailure("yt_dlp_unsupported_" f"platform:{platform}")

        source_url = str(source.get("canonical_url") or source.get("source_url") or "").rstrip("/")

        if (
            platform == "youtube"
            and "/channel/" in source_url
            and not source_url.endswith("/videos")
        ):
            source_url = f"{source_url}/videos"

        try:
            start_position = max(
                1,
                int(
                    source.get(
                        "_discovery_start_position",
                        1,
                    )
                ),
            )
        except (TypeError, ValueError):
            start_position = 1

        bounded = max(
            1,
            min(
                int(limit),
                30,
            ),
        )

        options = metadata_options(
            platform,
            {
                "quiet": True,
                "skip_download": True,
                "extract_flat": True,
                "playliststart": (start_position),
                "playlistend": (start_position + bounded - 1),
            },
        )

        extraction_error: Exception | None = None
        try:
            info = yt_dlp.YoutubeDL(options).extract_info(
                source_url,
                download=False,
            )
        except Exception as exc:
            extraction_error = exc
            info = None

        entries = (
            info.get("entries")
            if isinstance(
                info,
                dict,
            )
            else None
        )

        entries = (
            entries
            if isinstance(
                entries,
                list,
            )
            else [info]
        )

        used_public_fallback = False
        if platform == "youtube" and not any(
            _is_individual_youtube_entry(entry)
            for entry in entries
        ):
            entries = discover_youtube_public_entries(
                str(source.get("canonical_url") or source.get("source_url") or ""),
                start_position=start_position,
                limit=bounded,
            )
            used_public_fallback = bool(entries)

        if extraction_error is not None and not any(isinstance(entry, dict) for entry in entries):
            raise BackendFailure(
                "yt_dlp_discovery_failed:" f"{type(extraction_error).__name__}"
            ) from extraction_error

        account_id = str(
            (source.get("target_account_ids") or [source.get("target_account_id")])[0] or ""
        )

        result: list[NormalizedSourcePost] = []

        for entry in entries[:bounded]:
            if not isinstance(
                entry,
                dict,
            ):
                continue

            raw_url = _individual_entry_url(platform, entry)

            if not raw_url.startswith("https://"):
                continue

            post_url = canonical_url(raw_url)

            if platform == "youtube" and not ("/watch" in post_url or "/shorts/" in post_url):
                continue

            if platform == "tiktok" and "/video/" not in post_url:
                continue

            post_external_id = str(entry.get("id") or external_post_id(post_url))

            post_id = f"sp_{source['source_id']}_" f"{post_external_id}"

            duration = str(entry.get("duration") or "")

            media = NormalizedMediaItem(
                source_post_media_id=(f"spm_{post_id}_0"),
                source_post_id=post_id,
                media_index=0,
                media_type="video",
                canonical_post_url=(post_url),
                original_media_url=(post_url),
                resolver_backend=(self.backend_name),
                duration_seconds=(duration),
                thumbnail_url=str(entry.get("thumbnail") or ""),
            )

            text = str(entry.get("description") or entry.get("title") or "")

            collection_backend = (
                "youtube_public_html"
                if used_public_fallback
                else self.backend_name
            )

            result.append(
                NormalizedSourcePost(
                    source_post_id=post_id,
                    source_id=str(source["source_id"]),
                    target_account_id=(account_id),
                    platform=platform,
                    profile_url=(canonical_url(str(source.get("source_url") or ""))),
                    canonical_post_url=(post_url),
                    external_post_id=(post_external_id),
                    original_post_text=text,
                    published_at=str(
                        entry.get("upload_date")
                        or entry.get("timestamp")
                        or entry.get("published_at")
                        or ""
                    ),
                    author_name=str(entry.get("uploader") or ""),
                    author_handle=_source_author_handle(source, entry),
                    media_items=(media,),
                    engagement={
                        key: entry.get(key)
                        for key in (
                            "view_count",
                            "like_count",
                            "comment_count",
                        )
                        if entry.get(key) is not None
                    },
                    collection_backend=(collection_backend),
                    backend_version=(self.backend_version),
                    content_hash=(
                        stable_content_hash(
                            text,
                            [post_url],
                        )
                    ),
                    discovered_at=utc_now(),
                )
            )

        return result

    def discover_profile(
        self, source: dict[str, Any], *, limit: int
    ) -> ProviderResult[list[NormalizedSourcePost]]:
        try:
            posts = self.acquire(source, limit=limit)
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "PASS" if posts else "PARTIAL",
                data=posts,
                reason="" if posts else "no_videos_discovered",
            )
        except Exception as exc:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "FAILED",
                reason=str(exc) or f"{type(exc).__name__}:profile_discovery_failed",
                retryable=True,
            )
