#!/usr/bin/env python3
"""Download and Cloudinary-ingest one explicitly permitted source-post asset."""
from __future__ import annotations
import argparse, hashlib, json, mimetypes, os, shutil, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from config_loader import get_config
from sheets_client import TAB_DEFINITIONS, SheetsClient


def truthy(v: Any) -> bool: return str(v or "").lower() in {"1", "true", "yes"}

def record(client: SheetsClient, logical: str, key: str, value: str) -> dict[str, Any] | None:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return next((dict(row) for row in client._ws(logical).get_all_records() if str(row.get(key, "")) == value), None)

def permission_ok(client: SheetsClient, source_id: str) -> bool:
    client._ensure_tab("media_permissions", TAB_DEFINITIONS["media_permissions"])
    for row in client._ws("media_permissions").get_all_records():
        if str(row.get("source_id", "")) == source_id and not truthy(row.get("revoked")):
            return all(truthy(row.get(key)) for key in ("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption"))
    return False

def main() -> int:
    parser = argparse.ArgumentParser(description="ingest one permissioned direct source-post media asset")
    parser.add_argument("--source-post-media-id", required=True)
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
    media = record(client, "source_post_media", "source_post_media_id", args.source_post_media_id)
    if not media:
        print(json.dumps({"status": "BLOCKED", "reason": "source_post_media_not_found"})); return 1
    post = record(client, "source_posts", "source_post_id", str(media.get("source_post_id", "")))
    if not post or not permission_ok(client, str(post.get("source_id", ""))):
        print(json.dumps({"status": "BLOCKED", "reason": "active_direct_media_permission_missing"})); return 1
    url = str(media.get("original_media_url", "")); media_type = str(media.get("media_type", "")).lower()
    if media_type not in {"image", "video"} or not url.startswith("https://"):
        print(json.dumps({"status": "BLOCKED", "reason": "unsupported_or_non_https_media"})); return 1
    plan = {"status": "PLAN_ONLY", "source_post_media_id": args.source_post_media_id, "source_post_id": post["source_post_id"], "media_type": media_type, "would_download": True, "would_upload": True, "storage_target": f"output/direct_media/{args.source_post_media_id}"}
    target_dir = ROOT / "output" / "direct_media"; target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(url.split("?", 1)[0]).suffix or (".mp4" if media_type == "video" else ".jpg")
    local_path = target_dir / f"{args.source_post_media_id}{suffix}"
    try:
        with urllib.request.urlopen(url, timeout=45) as response, local_path.open("wb") as output:
            shutil.copyfileobj(response, output)
        digest = hashlib.sha256(local_path.read_bytes()).hexdigest(); mime = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
        import cloudinary.uploader
        uploaded = cloudinary.uploader.upload(str(local_path), resource_type="video" if media_type == "video" else "image", public_id=f"sns-growth/direct/{args.source_post_media_id}", overwrite=False)
        ws = client._ws("source_post_media"); headers = ws.row_values(1); row = next((i for i, item in enumerate(ws.get_all_records(), start=2) if str(item.get("source_post_media_id", "")) == args.source_post_media_id), 0)
        updates = {"download_status": "DOWNLOADED", "cloudinary_status": "UPLOADED", "cloudinary_public_id": str(uploaded.get("public_id", "")), "storage_url": str(uploaded.get("secure_url", "")), "content_hash": digest, "mime_type": mime, "last_error": "", "updated_at": datetime.now(timezone.utc).isoformat()}
        ws.batch_update([{"range": f"{chr(65 + headers.index(key))}{row}", "values": [[value]]} for key, value in updates.items() if key in headers], value_input_option="USER_ENTERED")
        print(json.dumps({**plan, "status": "INGESTED", "content_hash": digest, "would_download": False, "would_upload": False}, ensure_ascii=False, indent=2)); return 0
    except Exception as exc:
        print(json.dumps({**plan, "status": "FAILED", "reason": f"ingest_failed:{type(exc).__name__}"}, ensure_ascii=False, indent=2)); return 1

if __name__ == "__main__": raise SystemExit(main())
