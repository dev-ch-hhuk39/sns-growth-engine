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
from urllib.request import Request, urlopen

from generation.video_clip_materializer import probe_media_streams
from generation.media_platform_policy import can_attempt_physical_media, normalize_platform
from media.permission_ledger import evaluate_permission

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


def is_download_authorized(
    candidate: dict[str, Any],
    permission_rows: list[dict[str, Any]] | None = None,
    *,
    account_id: str = "",
) -> bool:
    rights = _text(candidate.get("rights_status")).lower()
    risk = _text(candidate.get("media_reuse_risk") or "low").lower()
    permission = _text(candidate.get("permission_status")).lower()
    if rights not in AUTHORIZED_RIGHTS or risk == "high" or permission in DENIED_PERMISSION:
        return False
    source_id = _text(candidate.get("source_id"))
    if not source_id or permission_rows is None:
        return False
    return bool(evaluate_permission(
        permission_rows,
        source_id,
        account_id=account_id,
        source_handle=_text(candidate.get("source_handle") or candidate.get("author_handle")),
        required_flags=("allow_download", "allow_cut"),
    )["allowed"])


def _x_handle(url: str, *, require_status: bool = False) -> str:
    pattern = r"^https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)"
    if require_status:
        pattern += r"/status/\d+(?:[/?#].*)?$"
    match = re.match(pattern, _text(url), flags=re.I)
    return match.group(1).lower() if match else ""


def x_registered_author_matches(url: str, registered_source: dict[str, Any]) -> bool:
    actual = _x_handle(url, require_status=True)
    expected = _text(registered_source.get("source_handle")).lstrip("@").lower()
    if not expected:
        expected = _x_handle(_text(registered_source.get("source_url")))
    return bool(actual and expected and actual == expected)


def _tiktok_handle(url: str, *, require_video: bool = False) -> str:
    pattern = r"^https?://(?:www\.)?tiktok\.com/@([A-Za-z0-9._-]+)"
    if require_video:
        pattern += r"/video/\d+(?:[/?#].*)?$"
    match = re.match(pattern, _text(url), flags=re.I)
    return match.group(1).lower() if match else ""


def tiktok_registered_author_matches(url: str, registered_source: dict[str, Any]) -> bool:
    actual = _tiktok_handle(url, require_video=True)
    expected = _text(registered_source.get("source_handle")).lstrip("@").lower()
    if not expected:
        expected = _tiktok_handle(_text(registered_source.get("source_url")))
    return bool(actual and expected and actual == expected)


def _tiktok_post_identity_url(candidate: dict[str, Any], source: dict[str, Any]) -> str:
    for row in (candidate, source):
        for key in (
            "canonical_post_url",
            "post_url",
            "canonical_video_url",
            "source_video_url",
            "original_video_url",
            "video_url",
            "url",
        ):
            value = _text(row.get(key))
            if _tiktok_handle(value, require_video=True):
                return value
    return ""


def _tiktok_direct_media_url(candidate: dict[str, Any], source: dict[str, Any]) -> str:
    for row in (candidate, source):
        for key in ("original_media_url", "direct_media_url", "media_url"):
            value = _text(row.get(key))
            host = (urlparse(value).hostname or "").lower()
            if value.startswith("https://") and (
                host.endswith(".tiktokcdn.com")
                or host.endswith(".byteoversea.com")
                or host.endswith(".ibytedtos.com")
            ):
                return value
    return ""


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


def _download_tiktok_direct(url: str, output: Path) -> None:
    """Download one already-resolved public TikTok media URL with a hard cap."""
    _validate_public_http_url(url)
    request = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"},
    )
    temporary = output.with_suffix(output.suffix + ".part")
    total = 0
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as destination:
            final_host = (urlparse(response.geturl()).hostname or "").lower()
            if not (
                final_host.endswith(".tiktokcdn.com")
                or final_host.endswith(".byteoversea.com")
                or final_host.endswith(".ibytedtos.com")
            ):
                raise RuntimeError("tiktok_media_redirect_host_rejected")
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("downloaded source exceeded bounded maximum size")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError("downloaded source exceeded bounded maximum size")
                destination.write(chunk)
        if total <= 0:
            raise RuntimeError("tiktok_direct_media_empty")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

def acquire_authorized_public_source(
    candidate: dict[str, Any],
    source: dict[str, Any],
    *,
    cache_root: str | Path,
    account_id: str,
    source_video_id: str,
    permission_rows: list[dict[str, Any]],
    registered_source: dict[str, Any] | None = None,
) -> Path:
    if not is_download_authorized(candidate, permission_rows, account_id=account_id):
        raise PermissionError("candidate is not explicitly authorized for source acquisition")
    cached = find_cached_source(cache_root, account_id, source_video_id, require_video=True)
    if cached is not None:
        return cached
    url = resolve_source_url(candidate, source)
    if not url:
        raise ValueError("no public source URL is available")
    platform = normalize_platform(
        candidate.get("source_platform") or candidate.get("platform")
        or source.get("source_platform") or source.get("platform"),
        url,
    )
    if not can_attempt_physical_media(platform, url):
        raise RuntimeError(f"physical_media_platform_deferred:{platform or 'unknown'}")
    if platform == "x" and not x_registered_author_matches(url, registered_source or {}):
        raise PermissionError("x_status_author_does_not_match_registered_source")
    tiktok_post_url = ""
    tiktok_direct_url = ""
    if platform == "tiktok":
        tiktok_post_url = _tiktok_post_identity_url(candidate, source)
        if not tiktok_registered_author_matches(tiktok_post_url, registered_source or {}):
            raise PermissionError("tiktok_video_author_does_not_match_registered_source")
        tiktok_direct_url = _tiktok_direct_media_url(candidate, source)
    _validate_public_http_url(url)

    directory = Path(cache_root).expanduser() / _safe_id(account_id)
    directory.mkdir(parents=True, exist_ok=True)
    prefix = _safe_id(source_video_id)
    if platform == "tiktok" and tiktok_direct_url:
        _download_tiktok_direct(tiktok_direct_url, directory / f"{prefix}-video.mp4")
    else:
        from yt_dlp import YoutubeDL

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
            ydl.extract_info(tiktok_post_url or url, download=True)
    acquired = find_cached_source(cache_root, account_id, source_video_id, require_video=True)
    if acquired is None:
        raise RuntimeError("physical acquisition completed without a usable cached source")
    if acquired.stat().st_size > MAX_DOWNLOAD_BYTES:
        acquired.unlink(missing_ok=True)
        raise RuntimeError("downloaded source exceeded bounded maximum size")
    return acquired
