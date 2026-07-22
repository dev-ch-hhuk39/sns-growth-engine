#!/usr/bin/env python3
"""Download and Cloudinary-ingest one explicitly permitted source-post asset."""
from __future__ import annotations
import argparse, hashlib, ipaddress, json, mimetypes, os, socket, subprocess, sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from config_loader import get_config
from media.direct_content_understanding import analyze_local_media
from sheets_client import TAB_DEFINITIONS, SheetsClient
from acquisition.ytdlp_runtime import metadata_options


def truthy(v: Any) -> bool: return str(v or "").lower() in {"1", "true", "yes"}

def record(client: SheetsClient, logical: str, key: str, value: str) -> dict[str, Any] | None:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    rows = client._call_with_rate_limit_retry(f"get_all_records:{logical}", lambda: client._ws(logical).get_all_records())
    return next((dict(row) for row in rows if str(row.get(key, "")) == value), None)

def permission_rows(client: SheetsClient) -> list[dict[str, Any]]:
    client._ensure_tab("media_permissions", TAB_DEFINITIONS["media_permissions"])
    return [
        dict(row)
        for row in client._call_with_rate_limit_retry(
            "get_all_records:media_permissions",
            lambda: client._ws("media_permissions").get_all_records(),
        )
    ]


def permission_ok_from_rows(rows: list[dict[str, Any]], source_id: str) -> bool:
    matches = [
        (index, row)
        for index, row in enumerate(rows)
        if str(row.get("source_id", "")) == source_id
    ]
    if not matches:
        return False
    # Permission rows are append/update history.  Selecting the first match
    # lets an obsolete denied row shadow the newer approval.  The latest
    # timestamp (and sheet order as a deterministic fallback) is the single
    # runtime authority; a latest revocation remains fail-closed.
    _index, current = max(
        matches,
        key=lambda item: (str(item[1].get("updated_at") or item[1].get("approved_at") or ""), item[0]),
    )
    if truthy(current.get("revoked")):
        return False
    if str(current.get("permission_status", "")).lower() != "approved":
        return False
    if str(current.get("rights_status", "")).lower() not in {"owned", "licensed", "approved_creator_clip"}:
        return False
    return all(truthy(current.get(key)) for key in (
        "allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption",
    ))


def permission_ok(client: SheetsClient, source_id: str) -> bool:
    return permission_ok_from_rows(permission_rows(client), source_id)

ALLOWLIST = {"youtube.com", "www.youtube.com", "youtu.be", "tiktok.com", "www.tiktok.com", "res.cloudinary.com"}
STREAM_HOST_SUFFIXES = {
    "googlevideo.com", "tiktokcdn.com", "tiktokcdn-us.com", "byteoversea.com",
    "ibytedtos.com", "akamaized.net", "muscdn.com", "cdninstagram.com", "fbcdn.net",
}

def col_letter(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26); result = chr(65 + remainder) + result
    return result

def safe_https_url(url: str, *, stream_url: bool = False) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    allowed = (STREAM_HOST_SUFFIXES | ALLOWLIST) if stream_url else ALLOWLIST
    if host not in allowed and not any(host.endswith("." + item) for item in allowed):
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


class _CheckedRedirect(HTTPRedirectHandler):
    """Follow only bounded HTTPS redirects that pass the same SSRF guard."""

    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request | None:
        if not safe_https_url(newurl, stream_url=True):
            raise RuntimeError("redirect_media_url_blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_direct_https_media(url: str, path: Path, *, media_type: str) -> None:
    """Download a resolved public image/video URL without extractor cookies.

    Threads OpenGraph media URLs are already direct CDN objects.  Routing them
    through yt-dlp loses carousel identity and can require an unsupported post
    extractor, so direct files use this constrained path instead.
    """
    if not safe_https_url(url, stream_url=True):
        raise RuntimeError("direct_media_url_blocked")
    limit = 300 * 1024 * 1024 if media_type == "video" else 20 * 1024 * 1024
    temporary = path.with_suffix(path.suffix + ".part")
    request = Request(url, headers={"User-Agent": "SNSGrowthEngine/1.0 media-ingest"})
    opener = build_opener(_CheckedRedirect())
    try:
        with opener.open(request, timeout=45) as response, temporary.open("wb") as handle:
            declared = int(response.headers.get("Content-Length") or "0")
            if declared and declared > limit:
                raise RuntimeError("media_size_limit_exceeded")
            written = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise RuntimeError("media_size_limit_exceeded")
                handle.write(chunk)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

def magic_mime(path: Path) -> str:
    head = path.read_bytes()[:32]
    if head.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if head.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if head[4:8] == b"ftyp": return "video/mp4"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP": return "image/webp"
    return ""

def probe_video(path: Path) -> dict[str, str]:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(path)], capture_output=True, text=True, timeout=30, check=True)
    data = json.loads(result.stdout); stream = next((item for item in data.get("streams", []) if item.get("width")), {})
    width, height = stream.get("width", ""), stream.get("height", "")
    duration = float(data.get("format", {}).get("duration") or 0)
    return {"duration_seconds": f"{duration:.2f}", "width": str(width), "height": str(height), "aspect_ratio": "9:16" if width and height and int(height) > int(width) else ""}

def download_with_ytdlp(url: str, path: Path) -> None:
    import yt_dlp
    def guard_resolved_stream(info: dict[str, Any]) -> None:
        resolved = str(info.get("url") or "")
        if resolved and not safe_https_url(resolved, stream_url=True):
            raise RuntimeError("resolved_media_url_blocked")

    def progress_guard(status: dict[str, Any]) -> None:
        info = status.get("info_dict") if isinstance(status, dict) else None
        if isinstance(info, dict):
            guard_resolved_stream(info)

    platform = "youtube" if "youtu" in url.lower() else "tiktok"
    opts = metadata_options(platform, {
        "quiet": True,
        "noplaylist": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(path.with_suffix(".%(ext)s")),
        "retries": 2,
        "socket_timeout": 45,
        "max_filesize": 300 * 1024 * 1024,
        "progress_hooks": [progress_guard],
    })
    with yt_dlp.YoutubeDL(opts) as ydl:
        planned = ydl.extract_info(url, download=False)
        if not isinstance(planned, dict):
            raise RuntimeError("yt_dlp_metadata_missing")
        requested = planned.get("requested_formats") or planned.get("requested_downloads") or [planned]
        for item in requested:
            if isinstance(item, dict):
                guard_resolved_stream(item)
        info = ydl.extract_info(url, download=True)
        actual = Path(ydl.prepare_filename(info))
        if not actual.exists():
            candidates = sorted(path.parent.glob(f"{path.stem}.*"), key=lambda item: item.stat().st_mtime, reverse=True)
            if not candidates:
                raise RuntimeError("yt_dlp_output_missing")
            actual = candidates[0]
        if actual != path:
            actual.replace(path)

def update_media_row(client: SheetsClient, source_post_media_id: str, fields: dict[str, Any]) -> None:
    ws = client._ws("source_post_media")
    headers = client._call_with_rate_limit_retry("read_headers:source_post_media", lambda: ws.row_values(1))
    rows = client._call_with_rate_limit_retry("get_all_records:source_post_media", lambda: ws.get_all_records())
    row_number = next((i for i, row in enumerate(rows, start=2) if str(row.get("source_post_media_id", "")) == source_post_media_id), 0)
    if not row_number: raise RuntimeError("source_post_media_row_missing")
    updates = [{"range": f"{col_letter(headers.index(key) + 1)}{row_number}", "values": [[str(value)]]} for key, value in fields.items() if key in headers]
    if updates:
        client._call_with_rate_limit_retry(
            "batch_update:source_post_media",
            lambda: ws.batch_update(updates, value_input_option="USER_ENTERED"),
        )

def upsert_media_asset(client: SheetsClient, post: dict[str, Any], media: dict[str, Any], *, storage_url: str, public_id: str, digest: str, mime: str, local_path: Path) -> str:
    asset_id = f"ma_{digest[:24]}"; ws = client._ensure_tab("media_assets", TAB_DEFINITIONS["media_assets"])
    headers = client._call_with_rate_limit_retry("read_headers:media_assets", lambda: ws.row_values(1))
    rows = client._call_with_rate_limit_retry("get_all_records:media_assets", lambda: ws.get_all_records())
    if any(str(row.get("media_id", "")) == asset_id for row in rows): return asset_id
    now = datetime.now(timezone.utc).isoformat()
    row = {"media_id": asset_id, "account_id": post.get("target_account_id", ""), "reference_post_id": post.get("source_post_id", ""), "source_platform": post.get("platform", ""), "source_post_url": post.get("canonical_post_url", ""), "original_media_url": media.get("original_media_url", ""), "storage_provider": "cloudinary", "storage_url": storage_url, "cloudinary_public_id": public_id, "media_type": media.get("media_type", ""), "mime_type": mime, "width": media.get("width", ""), "height": media.get("height", ""), "aspect_ratio": media.get("aspect_ratio", ""), "duration_seconds": media.get("duration_seconds", ""), "reuse_status": "APPROVED", "media_reuse_risk": "low", "downloaded_at": now, "uploaded_at": now, "used_count": "0", "local_path": str(local_path), "rights_status": post.get("rights_status", ""), "permission_status": post.get("permission_status", ""), "allow_download": "true", "allow_upload": "true", "upload_status": "UPLOADED"}
    client._call_with_rate_limit_retry("append_row:media_assets", lambda: ws.append_row([str(row.get(header, "")) for header in headers], value_input_option="USER_ENTERED"))
    verified = client._call_with_rate_limit_retry("get_all_records:media_assets:verify", lambda: ws.get_all_records())
    if not any(str(item.get("media_id", "")) == asset_id for item in verified):
        raise RuntimeError("media_asset_read_after_write_failed")
    return asset_id


def upsert_media_understanding(
    client: SheetsClient,
    post: dict[str, Any],
    media: dict[str, Any],
    analysis: dict[str, Any],
    *,
    content_hash: str,
) -> str:
    understanding_id = f"smu_{media.get('source_post_media_id', '')}"
    logical = "source_media_understanding"
    ws = client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    headers = client._call_with_rate_limit_retry(f"read_headers:{logical}", lambda: ws.row_values(1))
    rows = client._call_with_rate_limit_retry(f"get_all_records:{logical}", lambda: ws.get_all_records())
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "understanding_id": understanding_id,
        "source_post_media_id": media.get("source_post_media_id", ""),
        "source_post_id": post.get("source_post_id", ""),
        "source_id": post.get("source_id", ""),
        "account_id": post.get("target_account_id", ""),
        "platform": post.get("platform", ""),
        "media_type": media.get("media_type", ""),
        "status": analysis.get("status", "BLOCKED"),
        "provider_name": analysis.get("provider", ""),
        "visual_summary": analysis.get("visual_summary", ""),
        "visible_text": analysis.get("visible_text", ""),
        "main_claims_json": analysis.get("main_claims_json", "[]"),
        "safety_flags_json": analysis.get("safety_flags_json", "[]"),
        "ocr_text": analysis.get("ocr_text", ""),
        "ocr_hash": analysis.get("ocr_hash", ""),
        "transcript_text": analysis.get("transcript_text", ""),
        "transcript_hash": analysis.get("transcript_hash", ""),
        "transcription_provider": analysis.get("transcription_provider", ""),
        "transcript_status": analysis.get("transcript_status", ""),
        "representative_frame_timestamps_json": analysis.get("representative_frame_timestamps_json", "[]"),
        "representative_frame_count": analysis.get("representative_frame_count", "0"),
        "content_hash": content_hash,
        "blocked_reason": analysis.get("blocked_reason", ""),
        "created_at": now,
        "updated_at": now,
    }
    existing_number = next(
        (index for index, item in enumerate(rows, start=2) if str(item.get("understanding_id", "")) == understanding_id),
        0,
    )
    values = [str(row.get(header, "")) for header in headers]
    if existing_number:
        client._call_with_rate_limit_retry(
            f"update:{logical}",
            lambda: ws.batch_update(
                [{"range": f"A{existing_number}:{col_letter(len(headers))}{existing_number}", "values": [values]}],
                value_input_option="USER_ENTERED",
            ),
        )
    else:
        client._call_with_rate_limit_retry(
            f"append:{logical}",
            lambda: ws.append_row(values, value_input_option="USER_ENTERED"),
        )
    verified = client._call_with_rate_limit_retry(f"verify:{logical}", lambda: ws.get_all_records())
    if not any(
        str(item.get("understanding_id", "")) == understanding_id
        and str(item.get("content_hash", "")) == content_hash
        for item in verified
    ):
        raise RuntimeError("source_media_understanding_read_after_write_failed")
    return understanding_id

def select_pending_media_id(
    client: SheetsClient,
    account_id: str,
    *,
    permissions: list[dict[str, Any]] | None = None,
) -> str:
    """Return one deterministic pending asset for the requested account.

    Only assets whose source has an active direct-media permission can enter
    the candidate set.  This avoids selecting an older reference-only item,
    failing it later, and starving a permitted item behind it.
    """
    permissions = permission_rows(client) if permissions is None else permissions
    posts = {
        str(row.get("source_post_id", "")): row
        for row in client._ws("source_posts").get_all_records()
    }
    pending: list[tuple[int, str, str]] = []
    for media in client._ws("source_post_media").get_all_records():
        post = posts.get(str(media.get("source_post_id", "")))
        if not post or str(post.get("target_account_id", "")) != account_id:
            continue
        if not permission_ok_from_rows(permissions, str(post.get("source_id", ""))):
            continue
        if str(media.get("cloudinary_status", "")).upper() == "UPLOADED" and str(media.get("storage_url", "")):
            continue
        if str(media.get("download_status", "")).upper() in {"FAILED", "BLOCKED"}:
            continue
        url = str(media.get("original_media_url") or media.get("canonical_post_url") or "")
        platform = str(post.get("platform", "")).lower()
        if platform == "youtube" and not ("/watch" in url or "/shorts/" in url):
            continue
        if platform == "tiktok" and "/video/" not in url:
            continue
        if platform == "threads" and not safe_https_url(url, stream_url=True):
            continue
        media_id = str(media.get("source_post_media_id", ""))
        if media_id:
            # Prefer short-form individual videos for a bounded direct-media
            # slot. They are normally much smaller than a channel long-form
            # upload and still fall back to the same permitted source set.
            platform_priority = 0 if platform == "tiktok" else 1
            pending.append((platform_priority, str(media.get("created_at", "")), media_id))
    return sorted(pending)[0][2] if pending else ""


def source_post_media_bundle(client: SheetsClient, source_post_id: str) -> list[dict[str, Any]]:
    """Return the complete source-post media bundle in its original order."""
    rows = [
        dict(row)
        for row in client._ws("source_post_media").get_all_records()
        if str(row.get("source_post_id", "")) == source_post_id
    ]
    return sorted(
        rows,
        key=lambda row: (
            int(str(row.get("media_index", "0") or "0")),
            str(row.get("source_post_media_id", "")),
        ),
    )


def ingest_one(client: SheetsClient, post: dict[str, Any], media: dict[str, Any]) -> dict[str, Any]:
    source_post_media_id = str(media.get("source_post_media_id", ""))
    existing_understanding = record(client, "source_media_understanding", "source_post_media_id", source_post_media_id)
    already_uploaded = str(media.get("cloudinary_status", "")).upper() == "UPLOADED" and bool(str(media.get("storage_url", "")))
    if (
        already_uploaded
        and str((existing_understanding or {}).get("status", "")).upper() == "PASS"
    ):
        return {
            "status": "ALREADY_INGESTED",
            "source_post_media_id": source_post_media_id,
            "media_asset_id": str(media.get("media_asset_id", "")),
            "media_index": str(media.get("media_index", "")),
        }
    url = str(media.get("original_media_url") or media.get("canonical_post_url", ""))
    media_type = str(media.get("media_type", "")).lower()
    if media_type not in {"image", "video"} or not safe_https_url(url, stream_url=True):
        return {"status": "BLOCKED", "source_post_media_id": source_post_media_id, "reason": "unsupported_or_non_https_media"}

    target_dir = ROOT / "output" / "direct_media"
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".mp4" if media_type == "video" else ".jpg"
    local_path = target_dir / f"{source_post_media_id}{suffix}"
    try:
        platform = str(post.get("platform", "")).lower()
        is_direct_cdn = url != str(media.get("canonical_post_url", "")) or platform == "threads"
        if is_direct_cdn:
            download_direct_https_media(url, local_path, media_type=media_type)
        else:
            download_with_ytdlp(url, local_path)
        size_limit = 300 * 1024 * 1024 if media_type == "video" else 20 * 1024 * 1024
        if not local_path.exists() or local_path.stat().st_size > size_limit:
            raise RuntimeError("media_size_limit_exceeded")
        digest = hashlib.sha256()
        with local_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest_text = digest.hexdigest()
        mime = magic_mime(local_path)
        if not mime or not mime.startswith(media_type + "/"):
            raise RuntimeError("magic_bytes_or_mime_mismatch")
        details = probe_video(local_path) if media_type == "video" else {}
        analysis = analyze_local_media(
            local_path,
            media_type=media_type,
            duration_seconds=float(details.get("duration_seconds") or media.get("duration_seconds") or 0),
        )
        understanding_id = upsert_media_understanding(
            client,
            post,
            media,
            analysis,
            content_hash=digest_text,
        )
        update_media_row(client, source_post_media_id, {
            "understanding_status": analysis.get("status", "BLOCKED"),
            "visual_summary": analysis.get("visual_summary", ""),
            "visible_text": analysis.get("visible_text", ""),
            "ocr_hash": analysis.get("ocr_hash", ""),
            "transcript_hash": analysis.get("transcript_hash", ""),
            "representative_frame_count": analysis.get("representative_frame_count", "0"),
            "understanding_id": understanding_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if analysis.get("status") != "PASS":
            raise RuntimeError("media_content_understanding_blocked")
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
            api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
            api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
            secure=True,
        )
        uploaded = cloudinary.uploader.upload(
            str(local_path),
            resource_type="video" if media_type == "video" else "image",
            public_id=f"sns-growth/direct/{digest_text}",
            overwrite=False,
        )
        storage_url = str(uploaded.get("secure_url", ""))
        public_id = str(uploaded.get("public_id", ""))
        if not storage_url.startswith("https://res.cloudinary.com/"):
            raise RuntimeError("cloudinary_secure_url_missing")
        asset_id = upsert_media_asset(
            client,
            post,
            {**media, **details},
            storage_url=storage_url,
            public_id=public_id,
            digest=digest_text,
            mime=mime,
            local_path=local_path,
        )
        update_media_row(
            client,
            source_post_media_id,
            {
                "download_status": "DOWNLOADED",
                "cloudinary_status": "UPLOADED",
                "cloudinary_public_id": public_id,
                "storage_url": storage_url,
                "content_hash": digest_text,
                "mime_type": mime,
                "media_asset_id": asset_id,
                "understanding_status": "PASS",
                "understanding_id": understanding_id,
                "last_error": "",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **details,
            },
        )
        verified = record(client, "source_post_media", "source_post_media_id", source_post_media_id)
        if not verified or str(verified.get("media_asset_id", "")) != asset_id or str(verified.get("cloudinary_status", "")).upper() != "UPLOADED":
            raise RuntimeError("source_post_media_read_after_write_failed")
        return {
            "status": "INGESTED",
            "source_post_media_id": source_post_media_id,
            "media_asset_id": asset_id,
            "media_index": str(media.get("media_index", "")),
            "content_hash": digest_text,
            "understanding_status": "PASS",
            "understanding_provider": analysis.get("provider", ""),
        }
    except Exception as exc:
        # Provider-side access controls (for example a YouTube bot challenge)
        # are not a reason to fail the entire scheduled preparation run.  They
        # are persisted as a retryable, visible skip and never bypassed with
        # browser cookies or another authentication workaround.
        error_text = str(exc).lower()
        external_unavailable = any(marker in error_text for marker in (
            "sign in to confirm you\u2019re not a bot",
            "sign in to confirm you're not a bot",
            "not a bot",
            "http error 403",
            "http error 429",
        ))
        status = "SKIPPED_EXTERNAL_UNAVAILABLE" if external_unavailable else "FAILED"
        try:
            update_media_row(
                client,
                source_post_media_id,
                {
                    "download_status": "SKIPPED_EXTERNAL_UNAVAILABLE" if external_unavailable else "FAILED",
                    "cloudinary_status": "UPLOADED" if already_uploaded else ("SKIPPED" if external_unavailable else "FAILED"),
                    "last_error": f"ingest_{'skipped' if external_unavailable else 'failed'}:{type(exc).__name__}",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass
        return {
            "status": status,
            "source_post_media_id": source_post_media_id,
            "media_index": str(media.get("media_index", "")),
            "reason": f"ingest_{'skipped' if external_unavailable else 'failed'}:{type(exc).__name__}",
        }
    finally:
        local_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="ingest one permissioned direct source-post media asset")
    parser.add_argument("--source-post-media-id", default="")
    parser.add_argument("--source-post-id", default="", help="ingest the complete ordered media bundle for one source post")
    parser.add_argument("--account-id", choices=["night_scout", "liver_manager"], default="")
    parser.add_argument("--max-assets", type=int, default=10, help="hard cap for one source-post bundle")
    parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--apply", action="store_true"); parser.add_argument("--confirm-ingest", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_ingest:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-ingest"})); return 1
    gates = truthy(os.getenv("ALLOW_VIDEO_DOWNLOAD")) and truthy(os.getenv("ALLOW_CLOUDINARY_UPLOAD"))
    if args.apply and not gates:
        print(json.dumps({"status": "BLOCKED", "reason": "ALLOW_VIDEO_DOWNLOAD=true and ALLOW_CLOUDINARY_UPLOAD=true are required"})); return 1
    # Dry-run is deliberately offline: a real source-post lookup is an apply
    # precondition and must not authenticate to Sheets or touch a provider.
    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", "source_post_media_id": args.source_post_media_id, "would_lookup_sheets": True, "would_download": True, "would_upload": True, "network_fetch": False}, ensure_ascii=False, indent=2)); return 0
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    client._ensure_tab("source_posts", TAB_DEFINITIONS["source_posts"])
    client._ensure_tab("source_post_media", TAB_DEFINITIONS["source_post_media"])
    source_post_media_id = args.source_post_media_id
    source_post_id = args.source_post_id
    if source_post_id and source_post_media_id:
        print(json.dumps({"status": "BLOCKED", "reason": "choose_source_post_id_or_source_post_media_id"})); return 1
    try:
        permissions = permission_rows(client)
    except Exception:
        # A transient Sheets quota failure must never be interpreted as
        # permission.  End this preparation attempt without publishing; the
        # scheduled run can retry after the quota window resets.
        print(json.dumps({"status": "NO_PENDING_MEDIA", "reason": "sheets_permission_read_unavailable"})); return 0
    if source_post_id:
        bundle = source_post_media_bundle(client, source_post_id)
        source_post_media_id = str((bundle[0] if bundle else {}).get("source_post_media_id", ""))
    elif not source_post_media_id:
        source_post_media_id = select_pending_media_id(client, args.account_id, permissions=permissions)
    if not source_post_media_id:
        print(json.dumps({"status": "NO_PENDING_MEDIA", "reason": "no_pending_source_post_media_for_account"})); return 0
    media = record(client, "source_post_media", "source_post_media_id", source_post_media_id)
    if not media:
        print(json.dumps({"status": "BLOCKED", "reason": "source_post_media_not_found"})); return 1
    post = record(client, "source_posts", "source_post_id", str(media.get("source_post_id", "")))
    if not post or not permission_ok_from_rows(permissions, str(post.get("source_id", ""))):
        print(json.dumps({"status": "BLOCKED", "reason": "active_direct_media_permission_missing"})); return 1
    bundle = [media] if args.source_post_media_id else source_post_media_bundle(client, str(post["source_post_id"]))
    if not bundle:
        print(json.dumps({"status": "BLOCKED", "reason": "source_post_media_bundle_empty"})); return 1
    if args.max_assets < 1 or len(bundle) > args.max_assets:
        print(json.dumps({"status": "BLOCKED", "reason": "source_post_media_bundle_exceeds_cap", "asset_count": len(bundle), "max_assets": args.max_assets})); return 1
    results = [ingest_one(client, post, item) for item in bundle]
    failures = [row for row in results if row.get("status") == "FAILED"]
    skipped = [row for row in results if row.get("status") == "SKIPPED_EXTERNAL_UNAVAILABLE"]
    unsuccessful = failures + skipped
    status = (
        "INGESTED_BUNDLE" if not unsuccessful else
        "PARTIAL_FAILED" if failures and len(unsuccessful) < len(results) else
        "PARTIAL_SKIPPED" if skipped and len(unsuccessful) < len(results) else
        "SKIPPED_EXTERNAL_UNAVAILABLE" if skipped and not failures else
        "FAILED"
    )
    output = {
        "status": status,
        "source_post_id": post["source_post_id"],
        "asset_count": len(results),
        "ingested_count": len(results) - len(unsuccessful),
        "failed_count": len(failures),
        "skipped_count": len(skipped),
        "ordered_assets": results,
        "would_download": False,
        "would_upload": False,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not failures else 1

if __name__ == "__main__": raise SystemExit(main())
