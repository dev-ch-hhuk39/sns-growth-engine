#!/usr/bin/env python3
"""Source URL normalization helpers for registry dedupe and tests."""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_source_url(url: str) -> str:
    """Remove tracking query/fragment and normalize known account URL shapes."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    scheme = parts.scheme or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    if netloc in {"tiktok.com", "www.tiktok.com"}:
        netloc = "www.tiktok.com"
        if path.startswith("/@"):
            path = "/" + path.strip("/").split("/")[0]
    if netloc in {"www.youtube.com", "m.youtube.com"} and path.startswith("/channel/"):
        netloc = "youtube.com"
    if netloc == "youtube.com" and path.startswith("/channel/"):
        pass
    if netloc in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        netloc = "x.com"
    if netloc in {"threads.com", "www.threads.com"}:
        netloc = "www.threads.com"
    return urlunsplit((scheme, netloc, path, "", ""))
