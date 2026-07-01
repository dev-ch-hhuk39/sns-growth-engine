#!/usr/bin/env python3
"""Plan/apply rights-aware media asset ingestion.

External URLs are never downloaded here. Approved rights only create a
media_assets-shaped row for later human-reviewed media handling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import build_rights_decision, normalize_rights_status


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_id(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"ma_{digest}"


def file_metadata(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        return {"exists": False, "sha256": "", "size_bytes": "", "mime_type": "", "extension": p.suffix.lower()}
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return {
        "exists": True,
        "sha256": h.hexdigest(),
        "size_bytes": str(p.stat().st_size),
        "mime_type": mimetypes.guess_type(str(p))[0] or "",
        "extension": p.suffix.lower(),
    }


def detect_media_type(source: str, platform: str) -> str:
    low = source.lower()
    if platform in {"youtube", "tiktok"} or any(x in low for x in (".mp4", ".mov", ".webm", "/video/")):
        return "video"
    if any(low.endswith(x) for x in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return "image"
    return "unknown"


def build_media_asset_row(args: argparse.Namespace) -> dict[str, Any]:
    source = args.local_file or args.source_url
    meta = file_metadata(args.local_file) if args.local_file else {
        "exists": "",
        "sha256": "",
        "size_bytes": "",
        "mime_type": "",
        "extension": "",
    }
    media_type = detect_media_type(source, args.platform)
    rights_status = normalize_rights_status(args.rights_status)
    return {
        "media_asset_id": safe_id(f"{args.account_id}:{source}:{rights_status}"),
        "account_id": args.account_id,
        "source_platform": args.platform,
        "source_type": "local_file" if args.local_file else "external_url",
        "source_url": args.source_url,
        "original_media_url": args.source_url,
        "external_url": args.source_url,
        "local_path": str(Path(args.local_file).expanduser()) if args.local_file else "",
        "media_type": media_type,
        "rights_status": rights_status,
        "rights_policy": rights_status,
        "reuse_policy": "approved_reuse" if rights_status in {"owned", "licensed", "approved_creator_clip"} else "reference_only",
        "media_policy": "approved_media" if rights_status in {"owned", "licensed", "approved_creator_clip"} else "reference_only",
        "can_reuse_media": str(rights_status in {"owned", "licensed", "approved_creator_clip"}).lower(),
        "allow_download": "false",
        "allow_cut": str(rights_status in {"owned", "licensed", "approved_creator_clip"}).lower(),
        "allow_upload": str(rights_status in {"owned", "licensed", "approved_creator_clip"}).lower(),
        "storage_provider": "",
        "storage_url": "",
        "cloudinary_public_id": "",
        "upload_status": "NOT_UPLOADED",
        "status": "WAITING_REVIEW",
        "hash_sha256": meta["sha256"],
        "size_bytes": meta["size_bytes"],
        "mime_type": meta["mime_type"],
        "file_exists": str(meta["exists"]).lower() if meta["exists"] != "" else "",
        "created_at": now_iso(),
        "notes": "URL is registered only; no download/upload/post executed.",
    }


def build_ingest_plan(args: argparse.Namespace) -> dict[str, Any]:
    if not args.source_url and not args.local_file:
        return {"status": "BLOCKED", "blocked_reasons": ["--source-url or --local-file is required"], "media_assets": []}
    if args.source_url and args.local_file:
        return {"status": "BLOCKED", "blocked_reasons": ["Specify only one of --source-url or --local-file"], "media_assets": []}

    decision = build_rights_decision(args.rights_status, action="ingested/saved/reused")
    row = build_media_asset_row(args)
    blocked = []
    if not decision.allowed:
        blocked.append(decision.reason)
    if args.local_file and not file_metadata(args.local_file)["exists"]:
        blocked.append("local-file does not exist")

    status = "BLOCKED" if blocked else "WILL_APPLY" if args.apply else "PLAN_ONLY"
    return {
        "status": status,
        "account_id": args.account_id,
        "platform": args.platform,
        "rights_decision": decision.as_dict(),
        "media_download": False,
        "cloudinary_upload": False,
        "real_post": False,
        "blocked_reasons": blocked,
        "media_assets": [row],
    }


def append_media_assets(rows: list[dict[str, Any]]) -> int:
    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    ws = client._ws("media_assets")
    headers = ws.row_values(1)
    existing = {str(r.get("media_asset_id", "")) for r in ws.get_all_records()}
    to_append = [r for r in rows if str(r.get("media_asset_id", "")) not in existing]
    if to_append:
        ws.append_rows([["" if row.get(h) is None else str(row.get(h, "")) for h in headers] for row in to_append], value_input_option="USER_ENTERED")
    return len(to_append)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="rights-aware media asset ingestion")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--local-file", default="")
    parser.add_argument("--platform", required=True, choices=["youtube", "tiktok", "x", "threads", "local"])
    parser.add_argument("--rights-status", required=True)
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-ingest", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["beauty_account media ingestion is disabled"]}, ensure_ascii=False, indent=2))
        return 1
    plan = build_ingest_plan(args)
    if args.apply:
        if plan["status"] == "BLOCKED":
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 1
        if not args.confirm_ingest or not args.use_sheets:
            plan = {**plan, "status": "BLOCKED", "blocked_reasons": ["--apply requires --confirm-ingest --use-sheets"]}
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 1
        appended = append_media_assets(plan["media_assets"])
        plan = {**plan, "status": "APPLIED", "media_assets_appended": appended}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
