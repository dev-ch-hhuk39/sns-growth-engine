"""
WP3-C5: YouTube path provenance analyser.

Local URL parsing only. No network requests.
Raw URLs, handles, channel IDs, video IDs are never emitted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse, parse_qs


class PathShape(str, Enum):
    YOUTUBE_HANDLE_ROOT = "YOUTUBE_HANDLE_ROOT"
    YOUTUBE_HANDLE_TAB = "YOUTUBE_HANDLE_TAB"
    YOUTUBE_CHANNEL_ROOT = "YOUTUBE_CHANNEL_ROOT"
    YOUTUBE_CHANNEL_TAB = "YOUTUBE_CHANNEL_TAB"
    YOUTUBE_USER_ROOT = "YOUTUBE_USER_ROOT"
    YOUTUBE_USER_TAB = "YOUTUBE_USER_TAB"
    YOUTUBE_CUSTOM_ROOT = "YOUTUBE_CUSTOM_ROOT"
    YOUTUBE_CUSTOM_TAB = "YOUTUBE_CUSTOM_TAB"
    YOUTUBE_POST_URL = "YOUTUBE_POST_URL"
    YOUTUBE_OTHER = "YOUTUBE_OTHER"
    NON_YOUTUBE = "NON_YOUTUBE"
    EMPTY = "EMPTY"
    MALFORMED = "MALFORMED"


class TabKind(str, Enum):
    VIDEOS = "VIDEOS"
    SHORTS = "SHORTS"
    STREAMS = "STREAMS"
    LIVE = "LIVE"
    PLAYLISTS = "PLAYLISTS"
    COMMUNITY = "COMMUNITY"
    ABOUT = "ABOUT"
    FEATURED = "FEATURED"
    NONE = "NONE"
    OTHER = "OTHER"


class PostKind(str, Enum):
    WATCH = "WATCH"
    SHORTS = "SHORTS"
    LIVE = "LIVE"
    YOUTU_BE = "YOUTU_BE"
    NONE = "NONE"


# Tab slugs that correspond to known channel tabs
_TAB_SLUG_MAP: dict[str, TabKind] = {
    "videos": TabKind.VIDEOS,
    "shorts": TabKind.SHORTS,
    "streams": TabKind.STREAMS,
    "live": TabKind.LIVE,
    "playlists": TabKind.PLAYLISTS,
    "community": TabKind.COMMUNITY,
    "about": TabKind.ABOUT,
    "featured": TabKind.FEATURED,
}

# Allowed query keys (only flag presence, never emit value)
_ALLOWED_QUERY_KEYS = {"v", "list", "index", "t", "si"}

# Regex patterns (no capturing of identifying data in output)
_HANDLE_RE = re.compile(r"^/@[^/]+$")
_HANDLE_TAB_RE = re.compile(r"^/@[^/]+/([^/]+)$")
_CHANNEL_RE = re.compile(r"^/channel/[^/]+$")
_CHANNEL_TAB_RE = re.compile(r"^/channel/[^/]+/([^/]+)$")
_USER_RE = re.compile(r"^/user/[^/]+$")
_USER_TAB_RE = re.compile(r"^/user/[^/]+/([^/]+)$")
_CUSTOM_RE = re.compile(r"^/c/[^/]+$")
_CUSTOM_TAB_RE = re.compile(r"^/c/[^/]+/([^/]+)$")
_WATCH_RE = re.compile(r"^/watch$")
_WATCH_SHORTS_RE = re.compile(r"^/shorts/[^/]+$")
_WATCH_LIVE_RE = re.compile(r"^/live/[^/]+$")

_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com",
    "m.youtube.com", "music.youtube.com",
}
_YOUTU_BE_HOSTS = {"youtu.be", "www.youtu.be"}


@dataclass
class YouTubePathShape:
    """Safe output of YouTube URL shape analysis. No raw values emitted."""

    input_state: str          # ABSOLUTE_URL | RELATIVE | EMPTY | MALFORMED
    host_family: str          # YOUTUBE | YOUTU_BE | NON_YOUTUBE | NONE
    path_shape: PathShape
    tab_kind: TabKind
    post_kind: PostKind
    path_segment_count: int
    has_query: bool
    allowed_query_key_flags: list[str]   # list of allowed key names present
    has_fragment: bool
    post_identity_extracted: bool


def _classify_tab_slug(slug: str) -> TabKind:
    return _TAB_SLUG_MAP.get(slug.lower(), TabKind.OTHER)


def analyse_youtube_url(raw_url: str) -> YouTubePathShape:
    """
    Analyse a URL and return safe shape metadata. No raw URL data emitted.
    """
    if not isinstance(raw_url, str):
        raw_url = ""

    stripped = raw_url.strip()

    if not stripped:
        return YouTubePathShape(
            input_state="EMPTY",
            host_family="NONE",
            path_shape=PathShape.EMPTY,
            tab_kind=TabKind.NONE,
            post_kind=PostKind.NONE,
            path_segment_count=0,
            has_query=False,
            allowed_query_key_flags=[],
            has_fragment=False,
            post_identity_extracted=False,
        )

    # Attempt parse
    try:
        parsed = urlparse(stripped)
    except Exception:
        return YouTubePathShape(
            input_state="MALFORMED",
            host_family="NONE",
            path_shape=PathShape.MALFORMED,
            tab_kind=TabKind.NONE,
            post_kind=PostKind.NONE,
            path_segment_count=0,
            has_query=False,
            allowed_query_key_flags=[],
            has_fragment=False,
            post_identity_extracted=False,
        )

    # Determine input_state
    if parsed.scheme in ("http", "https") and parsed.netloc:
        input_state = "ABSOLUTE_URL"
    elif stripped.startswith("/"):
        input_state = "RELATIVE"
    else:
        input_state = "MALFORMED"

    # Host family
    host = parsed.netloc.lower().split(":")[0] if parsed.netloc else ""
    if host in _YOUTUBE_HOSTS:
        host_family = "YOUTUBE"
    elif host in _YOUTU_BE_HOSTS:
        host_family = "YOUTU_BE"
    elif host:
        host_family = "NON_YOUTUBE"
    else:
        host_family = "NONE"

    # Non-YouTube => simple return
    if host_family == "NON_YOUTUBE":
        path_segs = [s for s in parsed.path.split("/") if s]
        has_query = bool(parsed.query)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        present = sorted(k for k in qs if k in _ALLOWED_QUERY_KEYS)
        return YouTubePathShape(
            input_state=input_state,
            host_family=host_family,
            path_shape=PathShape.NON_YOUTUBE,
            tab_kind=TabKind.NONE,
            post_kind=PostKind.NONE,
            path_segment_count=len(path_segs),
            has_query=has_query,
            allowed_query_key_flags=present,
            has_fragment=bool(parsed.fragment),
            post_identity_extracted=False,
        )

    path = parsed.path or "/"
    path_segs = [s for s in path.split("/") if s]
    seg_count = len(path_segs)
    has_query = bool(parsed.query)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    present_keys = sorted(k for k in qs if k in _ALLOWED_QUERY_KEYS)
    has_fragment = bool(parsed.fragment)

    # youtu.be => always a post
    if host_family == "YOUTU_BE":
        # youtu.be/<video_id>
        post_identity_extracted = seg_count >= 1
        return YouTubePathShape(
            input_state=input_state,
            host_family=host_family,
            path_shape=PathShape.YOUTUBE_POST_URL,
            tab_kind=TabKind.NONE,
            post_kind=PostKind.YOUTU_BE,
            path_segment_count=seg_count,
            has_query=has_query,
            allowed_query_key_flags=present_keys,
            has_fragment=has_fragment,
            post_identity_extracted=post_identity_extracted,
        )

    # youtube.com paths
    # /watch?v=...
    if _WATCH_RE.match(path):
        has_v = "v" in qs and bool(qs["v"][0].strip())
        return YouTubePathShape(
            input_state=input_state,
            host_family=host_family,
            path_shape=PathShape.YOUTUBE_POST_URL,
            tab_kind=TabKind.NONE,
            post_kind=PostKind.WATCH,
            path_segment_count=seg_count,
            has_query=has_query,
            allowed_query_key_flags=present_keys,
            has_fragment=has_fragment,
            post_identity_extracted=has_v,
        )

    # /shorts/<id>
    if _WATCH_SHORTS_RE.match(path):
        return YouTubePathShape(
            input_state=input_state,
            host_family=host_family,
            path_shape=PathShape.YOUTUBE_POST_URL,
            tab_kind=TabKind.NONE,
            post_kind=PostKind.SHORTS,
            path_segment_count=seg_count,
            has_query=has_query,
            allowed_query_key_flags=present_keys,
            has_fragment=has_fragment,
            post_identity_extracted=True,
        )

    # /live/<id>
    if _WATCH_LIVE_RE.match(path):
        return YouTubePathShape(
            input_state=input_state,
            host_family=host_family,
            path_shape=PathShape.YOUTUBE_POST_URL,
            tab_kind=TabKind.NONE,
            post_kind=PostKind.LIVE,
            path_segment_count=seg_count,
            has_query=has_query,
            allowed_query_key_flags=present_keys,
            has_fragment=has_fragment,
            post_identity_extracted=True,
        )

    # /@handle or /@handle/<tab>
    if path.startswith("/@"):
        m_tab = _HANDLE_TAB_RE.match(path)
        if m_tab:
            tab_slug = m_tab.group(1)
            tab_kind = _classify_tab_slug(tab_slug)
            return YouTubePathShape(
                input_state=input_state,
                host_family=host_family,
                path_shape=PathShape.YOUTUBE_HANDLE_TAB,
                tab_kind=tab_kind,
                post_kind=PostKind.NONE,
                path_segment_count=seg_count,
                has_query=has_query,
                allowed_query_key_flags=present_keys,
                has_fragment=has_fragment,
                post_identity_extracted=False,
            )
        if _HANDLE_RE.match(path):
            return YouTubePathShape(
                input_state=input_state,
                host_family=host_family,
                path_shape=PathShape.YOUTUBE_HANDLE_ROOT,
                tab_kind=TabKind.NONE,
                post_kind=PostKind.NONE,
                path_segment_count=seg_count,
                has_query=has_query,
                allowed_query_key_flags=present_keys,
                has_fragment=has_fragment,
                post_identity_extracted=False,
            )

    # /channel/<id> or /channel/<id>/<tab>
    if path.startswith("/channel/"):
        m_tab = _CHANNEL_TAB_RE.match(path)
        if m_tab:
            tab_kind = _classify_tab_slug(m_tab.group(1))
            return YouTubePathShape(
                input_state=input_state,
                host_family=host_family,
                path_shape=PathShape.YOUTUBE_CHANNEL_TAB,
                tab_kind=tab_kind,
                post_kind=PostKind.NONE,
                path_segment_count=seg_count,
                has_query=has_query,
                allowed_query_key_flags=present_keys,
                has_fragment=has_fragment,
                post_identity_extracted=False,
            )
        if _CHANNEL_RE.match(path):
            return YouTubePathShape(
                input_state=input_state,
                host_family=host_family,
                path_shape=PathShape.YOUTUBE_CHANNEL_ROOT,
                tab_kind=TabKind.NONE,
                post_kind=PostKind.NONE,
                path_segment_count=seg_count,
                has_query=has_query,
                allowed_query_key_flags=present_keys,
                has_fragment=has_fragment,
                post_identity_extracted=False,
            )

    # /user/<name> or /user/<name>/<tab>
    if path.startswith("/user/"):
        m_tab = _USER_TAB_RE.match(path)
        if m_tab:
            tab_kind = _classify_tab_slug(m_tab.group(1))
            return YouTubePathShape(
                input_state=input_state,
                host_family=host_family,
                path_shape=PathShape.YOUTUBE_USER_TAB,
                tab_kind=tab_kind,
                post_kind=PostKind.NONE,
                path_segment_count=seg_count,
                has_query=has_query,
                allowed_query_key_flags=present_keys,
                has_fragment=has_fragment,
                post_identity_extracted=False,
            )
        if _USER_RE.match(path):
            return YouTubePathShape(
                input_state=input_state,
                host_family=host_family,
                path_shape=PathShape.YOUTUBE_USER_ROOT,
                tab_kind=TabKind.NONE,
                post_kind=PostKind.NONE,
                path_segment_count=seg_count,
                has_query=has_query,
                allowed_query_key_flags=present_keys,
                has_fragment=has_fragment,
                post_identity_extracted=False,
            )

    # /c/<name> or /c/<name>/<tab>
    if path.startswith("/c/"):
        m_tab = _CUSTOM_TAB_RE.match(path)
        if m_tab:
            tab_kind = _classify_tab_slug(m_tab.group(1))
            return YouTubePathShape(
                input_state=input_state,
                host_family=host_family,
                path_shape=PathShape.YOUTUBE_CUSTOM_TAB,
                tab_kind=tab_kind,
                post_kind=PostKind.NONE,
                path_segment_count=seg_count,
                has_query=has_query,
                allowed_query_key_flags=present_keys,
                has_fragment=has_fragment,
                post_identity_extracted=False,
            )
        if _CUSTOM_RE.match(path):
            return YouTubePathShape(
                input_state=input_state,
                host_family=host_family,
                path_shape=PathShape.YOUTUBE_CUSTOM_ROOT,
                tab_kind=TabKind.NONE,
                post_kind=PostKind.NONE,
                path_segment_count=seg_count,
                has_query=has_query,
                allowed_query_key_flags=present_keys,
                has_fragment=has_fragment,
                post_identity_extracted=False,
            )

    # Fallback
    return YouTubePathShape(
        input_state=input_state,
        host_family=host_family,
        path_shape=PathShape.YOUTUBE_OTHER,
        tab_kind=TabKind.NONE,
        post_kind=PostKind.NONE,
        path_segment_count=seg_count,
        has_query=has_query,
        allowed_query_key_flags=present_keys,
        has_fragment=has_fragment,
        post_identity_extracted=False,
    )


def shape_to_safe_dict(shape: YouTubePathShape) -> dict:
    """Convert shape to JSON-safe dict with no raw values."""
    return {
        "input_state": shape.input_state,
        "host_family": shape.host_family,
        "path_shape": shape.path_shape.value,
        "tab_kind": shape.tab_kind.value,
        "post_kind": shape.post_kind.value,
        "path_segment_count": shape.path_segment_count,
        "has_query": shape.has_query,
        "allowed_query_key_flags": shape.allowed_query_key_flags,
        "has_fragment": shape.has_fragment,
        "post_identity_extracted": shape.post_identity_extracted,
    }
