"""Rights-gated local acquisition of public video sources for clip materialization.

This module only downloads to a deterministic local cache. It never writes Sheets,
uploads media, changes review status, or posts to social networks.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from generation.video_clip_materializer import probe_media_streams

AUTHORIZED_RIGHTS = {
    "allowed",
    "approved",
    "approved_creator_clip",
    "creator_approved",
    "owned",
    "owner",
    "granted",
    "permission_granted",
}
DENIED_PERMISSION = {"denied", "not_allowed", "rejected", "revoked"}
MAX_DOWNLOAD_BYTES = 750 * 1024 * 1024


def _text(value: Any) -> str:
    return str(value or "").strip()


def is_download_authorized(candidate: dict[str, Any]) -> bool:
    rights = _text(candidate.get("rights_status")).lower()
    risk = _text(candidate.get("media_reuse_risk") or "low").lower()
    permission = _text(candidate.get("permission_status")).lower()
    return rights in AUTHORIZED_RIGHTS and risk != "high" and permission not in DENIED_PERMISSION


def resolve_source_url(candidate: dict[str, Any], source: dict[str, Any]) -> str:
    keys = (
        "source_video_url",
        "video_url",
        "source_url",
        "canonical_video_url",
        "original_video_url",
        "canonical_url",
        "original_url",
        "post_url",
        "url",
    )
    for row in (candidate, source):
        for key in keys:
            value = _text(row.get(key))
            if value.startswith("http://") or value.startswith("https://"):
                return value
    return ""


def _validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source URL must be public HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("credential-bearing source URLs are not allowed")
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("source hostname could not be resolved") from exc
    if not infos:
        raise ValueError("source hostname resolved to no addresses")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("private or non-routable source address is not allowed")


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return safe[:120] or "source"


def _has_video_stream(path: Path) -> bool:
    try:
        probe = probe_media_streams(path)
    except Exception:
        return False
    return int(probe.get("video_stream_count") or 0) >= 1 and int(probe.get("width") or 0) > 0 and int(probe.get("height") or 0) > 0


def find_cached_source(
    cache_root: str | Path,
    account_id: str,
    source_video_id: str,
    *,
    require_video: bool = False,
) -> Path | None:
    directory = Path(cache_root).expanduser() / _safe_id(account_id)
    prefix = _safe_id(source_video_id)
    if not directory.is_dir():
        return None
    files: list[Path] = []
    for pattern in (prefix + ".*", prefix + "-video.*"):
        files.extend(
            p for p in directory.glob(pattern)
            if p.is_file() and p.stat().st_size > 0 and p.suffix.lower() not in {".part", ".ytdl", ".json"}
        )
    deduped = list({p.resolve(): p for p in files}.values())
    if require_video:
        deduped = [p for p in deduped if _has_video_stream(p)]
    if not deduped:
        return None
    deduped.sort(key=lambda p: (p.stat().st_mtime, p.stat().st_size), reverse=True)
    return deduped[0]

def acquire_authorized_public_source(
    candidate: dict[str, Any],
    source: dict[str, Any],
    *,
    cache_root: str | Path,
    account_id: str,
    source_video_id: str,
) -> Path:
    if not is_download_authorized(candidate):
        raise PermissionError("candidate is not explicitly authorized for source acquisition")
    cached = find_cached_source(cache_root, account_id, source_video_id, require_video=True)
    if cached is not None:
        return cached
    url = resolve_source_url(candidate, source)
    if not url:
        raise ValueError("no public source URL is available")
    _validate_public_http_url(url)
    from yt_dlp import YoutubeDL

    directory = Path(cache_root).expanduser() / _safe_id(account_id)
    directory.mkdir(parents=True, exist_ok=True)
    prefix = _safe_id(source_video_id)
    outtmpl = str(directory / f"{prefix}-video.%(ext)s")
    options = {
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "max_filesize": MAX_DOWNLOAD_BYTES,
        "overwrites": False,
        "continuedl": True,
        "socket_timeout": 30,
    }
    with YoutubeDL(options) as ydl:
        ydl.extract_info(url, download=True)
    acquired = find_cached_source(cache_root, account_id, source_video_id, require_video=True)
    if acquired is None:
        raise RuntimeError("yt-dlp completed without a usable cached source")
    if acquired.stat().st_size > MAX_DOWNLOAD_BYTES:
        acquired.unlink(missing_ok=True)
        raise RuntimeError("downloaded source exceeded bounded maximum size")
    return acquired
