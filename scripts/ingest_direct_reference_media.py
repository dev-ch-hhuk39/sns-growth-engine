#!/usr/bin/env python3
"""Download and Cloudinary-ingest one explicitly permitted source-post asset."""
from __future__ import annotations
import argparse, hashlib, ipaddress, json, mimetypes, os, socket, subprocess, sys
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from config_loader import get_config
from sheets_client import TAB_DEFINITIONS, SheetsClient


def truthy(v: Any) -> bool: return str(v or "").lower() in {"1", "true", "yes"}

def record(client: SheetsClient, logical: str, key: str, value: str) -> dict[str, Any] | None:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    rows = client._call_with_rate_limit_retry(f"get_all_records:{logical}", lambda: client._ws(logical).get_all_records())
    return next((dict(row) for row in rows if str(row.get(key, "")) == value), None)

def permission_ok(client: SheetsClient, source_id: str) -> bool:
    client._ensure_tab("media_permissions", TAB_DEFINITIONS["media_permissions"])
    rows = client._call_with_rate_limit_retry("get_all_records:media_permissions", lambda: client._ws("media_permissions").get_all_records())
    for row in rows:
        if str(row.get("source_id", "")) == source_id and not truthy(row.get("revoked")):
            return all(truthy(row.get(key)) for key in ("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption"))
    return False

ALLOWLIST = {"youtube.com", "www.youtube.com", "youtu.be", "tiktok.com", "www.tiktok.com", "res.cloudinary.com"}

def col_letter(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26); result = chr(65 + remainder) + result
    return result

def safe_https_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host not in ALLOWLIST and not any(host.endswith("." + allowed) for allowed in ALLOWLIST):
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
    opts = {
        "quiet": True,
        "noplaylist": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(path.with_suffix(".%(ext)s")),
        "retries": 2,
        "socket_timeout": 45,
        "max_filesize": 300 * 1024 * 1024,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
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
    client._call_with_rate_limit_retry("append_row:media_assets", lambda: ws.append_row([str(row.get(header, "")) for header in headers], value_input_option="USER_ENTERED")); return asset_id

def select_pending_media_id(client: SheetsClient, account_id: str) -> str:
    """Return one deterministic pending asset for the requested account.

    This selector only chooses a row.  The existing permission, URL, download,
    and Cloudinary gates still run before any external operation.
    """
    posts = {
        str(row.get("source_post_id", "")): row
        for row in client._ws("source_posts").get_all_records()
    }
    pending: list[tuple[int, str, str]] = []
    for media in client._ws("source_post_media").get_all_records():
        post = posts.get(str(media.get("source_post_id", "")))
        if not post or str(post.get("target_account_id", "")) != account_id:
            continue
        if str(media.get("cloudinary_status", "")).upper() == "UPLOADED" and str(media.get("storage_url", "")):
            continue
        if str(media.get("download_status", "")).upper() in {"FAILED", "BLOCKED"}:
            continue
        url = str(media.get("canonical_post_url") or media.get("original_media_url") or "")
        platform = str(post.get("platform", "")).lower()
        if platform == "youtube" and not ("/watch" in url or "/shorts/" in url):
            continue
        if platform == "tiktok" and "/video/" not in url:
            continue
        media_id = str(media.get("source_post_media_id", ""))
        if media_id:
            # Prefer short-form individual videos for a bounded direct-media
            # slot. They are normally much smaller than a channel long-form
            # upload and still fall back to the same permitted source set.
            platform_priority = 0 if platform == "tiktok" else 1
            pending.append((platform_priority, str(media.get("created_at", "")), media_id))
    return sorted(pending)[0][2] if pending else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="ingest one permissioned direct source-post media asset")
    parser.add_argument("--source-post-media-id", default="")
    parser.add_argument("--account-id", choices=["night_scout", "liver_manager"], default="")
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
    source_post_media_id = args.source_post_media_id or select_pending_media_id(client, args.account_id)
    if not source_post_media_id:
        print(json.dumps({"status": "NO_PENDING_MEDIA", "reason": "no_pending_source_post_media_for_account"})); return 0
    media = record(client, "source_post_media", "source_post_media_id", source_post_media_id)
    if not media:
        print(json.dumps({"status": "BLOCKED", "reason": "source_post_media_not_found"})); return 1
    post = record(client, "source_posts", "source_post_id", str(media.get("source_post_id", "")))
    if not post or not permission_ok(client, str(post.get("source_id", ""))):
        print(json.dumps({"status": "BLOCKED", "reason": "active_direct_media_permission_missing"})); return 1
    url = str(media.get("canonical_post_url") or media.get("original_media_url", "")); media_type = str(media.get("media_type", "")).lower()
    if media_type not in {"image", "video"} or not safe_https_url(url):
        print(json.dumps({"status": "BLOCKED", "reason": "unsupported_or_non_https_media"})); return 1
    plan = {"status": "PLAN_ONLY", "source_post_media_id": source_post_media_id, "source_post_id": post["source_post_id"], "media_type": media_type, "would_download": True, "would_upload": True, "storage_target": f"output/direct_media/{source_post_media_id}"}
    target_dir = ROOT / "output" / "direct_media"; target_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".mp4" if media_type == "video" else ".jpg"
    local_path = target_dir / f"{source_post_media_id}{suffix}"
    try:
        download_with_ytdlp(url, local_path)
        size_limit = 300 * 1024 * 1024 if media_type == "video" else 20 * 1024 * 1024
        if not local_path.exists() or local_path.stat().st_size > size_limit: raise RuntimeError("media_size_limit_exceeded")
        digest = hashlib.sha256();
        with local_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
        digest_text = digest.hexdigest(); mime = magic_mime(local_path)
        if not mime or not mime.startswith(media_type + "/"): raise RuntimeError("magic_bytes_or_mime_mismatch")
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
            api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
            api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
            secure=True,
        )
        uploaded = cloudinary.uploader.upload(str(local_path), resource_type="video" if media_type == "video" else "image", public_id=f"sns-growth/direct/{digest_text}", overwrite=False)
        storage_url = str(uploaded.get("secure_url", "")); public_id = str(uploaded.get("public_id", ""))
        if not storage_url.startswith("https://res.cloudinary.com/"): raise RuntimeError("cloudinary_secure_url_missing")
        details = probe_video(local_path) if media_type == "video" else {}
        asset_id = upsert_media_asset(client, post, {**media, **details}, storage_url=storage_url, public_id=public_id, digest=digest_text, mime=mime, local_path=local_path)
        update_media_row(client, source_post_media_id, {"download_status": "DOWNLOADED", "cloudinary_status": "UPLOADED", "cloudinary_public_id": public_id, "storage_url": storage_url, "content_hash": digest_text, "mime_type": mime, "media_asset_id": asset_id, "last_error": "", "updated_at": datetime.now(timezone.utc).isoformat(), **details})
        local_path.unlink(missing_ok=True)
        print(json.dumps({**plan, "status": "INGESTED", "content_hash": digest_text, "media_asset_id": asset_id, "would_download": False, "would_upload": False}, ensure_ascii=False, indent=2)); return 0
    except Exception as exc:
        local_path.unlink(missing_ok=True)
        try:
            update_media_row(client, source_post_media_id, {
                "download_status": "FAILED", "cloudinary_status": "FAILED",
                "last_error": f"ingest_failed:{type(exc).__name__}",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
        print(json.dumps({**plan, "status": "FAILED", "reason": f"ingest_failed:{type(exc).__name__}"}, ensure_ascii=False, indent=2)); return 1

if __name__ == "__main__": raise SystemExit(main())
