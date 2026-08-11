#!/usr/bin/env python3
"""Verify actual Golden bytes through the shared reference-first review path."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.models import (  # noqa: E402
    NormalizedMediaItem,
    NormalizedSourcePost,
    stable_content_hash,
    validate_source_post,
)
from acquisition.x_exact_status import validate_exact_status_provenance  # noqa: E402
from config_loader import get_config  # noqa: E402
from generation.reference_first_router import choose_reference_first_route  # noqa: E402
from generation.video_clip_materializer import probe_media_streams  # noqa: E402
from media.permission_ledger import evaluate_permission  # noqa: E402
from process_threads_queue import ELIGIBLE_STATUSES  # noqa: E402
from public_post_quality import (  # noqa: E402
    final_public_post_validator,
    generate_production_post,
)
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402


def _video_id(url: str) -> str:
    match = re.search(r"(?:v=|/shorts/|/status/|/video/)([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else ""


def _find_file(item: dict[str, Any], directories: list[Path]) -> Path | None:
    needles = [_video_id(str(item["url"])), str(item.get("source_handle", "")).lstrip("@").lower()]
    for directory in directories:
        for path in directory.glob("*.mp4"):
            lowered = path.name.lower()
            if any(needle and needle.lower() in lowered for needle in needles):
                return path
    return None


def _find_metadata(item: dict[str, Any], directories: list[Path]) -> dict[str, Any]:
    needles = [_video_id(str(item["url"])), str(item.get("source_handle", "")).lstrip("@").lower()]
    for directory in directories:
        for path in directory.glob("*.info.json"):
            lowered = path.name.lower()
            if any(needle and needle.lower() in lowered for needle in needles):
                payload = json.loads(path.read_text(encoding="utf-8"))
                return payload if isinstance(payload, dict) else {}
    return {}


def _permission_rows(use_sheets: bool) -> list[dict[str, Any]]:
    if not use_sheets:
        return []
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    return [dict(row) for row in read_records_safely(client, "media_permissions")]


def verify_item(
    item: dict[str, Any],
    path: Path | None,
    metadata: dict[str, Any],
    permissions: list[dict[str, Any]],
) -> dict[str, Any]:
    account_id = str(item["account_id"])
    source_id = str(item["source_id"])
    url = str(item["url"])
    source_text = str(metadata.get("description") or item.get("source_text") or "")
    permission = evaluate_permission(
        permissions,
        source_id,
        account_id=account_id,
        source_handle=str(item.get("source_handle") or ""),
        required_flags=(
            "allow_download",
            "allow_cloudinary_storage",
            "allow_original_repost",
            "allow_new_caption",
        ),
    )
    probe: dict[str, Any] = {}
    if path and path.is_file() and path.stat().st_size:
        probe = probe_media_streams(path)
    post_id = f"golden_{source_id}_{_video_id(url)}"
    media = NormalizedMediaItem(
        source_post_media_id=f"spm_{post_id}_0",
        source_post_id=post_id,
        media_index=0,
        media_type="video",
        canonical_post_url=url,
        original_media_url=url,
        resolver_backend="public_embed_direct_http" if "tiktok.com/" in url else "yt_dlp",
        mime_type="video/mp4",
        width=str(probe.get("width") or ""),
        height=str(probe.get("height") or ""),
        duration_seconds=str(probe.get("duration_seconds") or ""),
    )
    platform = "x" if "x.com/" in url else ("tiktok" if "tiktok.com/" in url else "youtube")
    provenance = (
        validate_exact_status_provenance(url, item, metadata)
        if platform == "x"
        else {"status": "PASS", "reasons": []}
    )
    post = NormalizedSourcePost(
        source_post_id=post_id,
        source_id=source_id,
        target_account_id=account_id,
        platform=platform,
        profile_url=(
            url.split("/status/", 1)[0]
            if platform == "x"
            else (url.split("/video/", 1)[0] if platform == "tiktok" else url)
        ),
        canonical_post_url=url.rstrip("/"),
        external_post_id=_video_id(url),
        original_post_text=source_text,
        published_at="",
        author_handle=str(item.get("source_handle") or "").lstrip("@"),
        media_items=(media,),
        collection_backend="public_embed_direct_http" if platform == "tiktok" else "yt_dlp",
        backend_version="physical-golden",
        content_hash=stable_content_hash(source_text, [url]),
        discovered_at="2026-08-11T00:00:00+00:00",
        detail_status="COMPLETE",
    )
    source_errors = validate_source_post(post)
    understanding = {
        "status": "PASS" if source_text and probe else "BLOCKED",
        "summary": source_text,
        "transcript_status": "NOT_REQUIRED_FOR_DIRECT_REFERENCE_MEDIA",
        "standalone_segment_confirmed": False,
        "standalone_story_score": 0,
        "clip_worthy": False,
    }
    route = choose_reference_first_route(
        desired_route="direct_reference_media",
        source_has_direct_media_permission=bool(permission["allowed"]),
        content_understanding=understanding,
    )
    generated = generate_production_post(
        account_id,
        batch_id="physical-golden-20260811",
        content_type="reference_text_generation",
        reference_signal=source_text,
    )
    public_text = str(generated.get("public_post_text") or "")
    public_validation = final_public_post_validator(public_text, account_id)
    queue_status = "WAITING_REVIEW" if (
        not source_errors
        and provenance["status"] == "PASS"
        and permission["allowed"]
        and route.get("status") == "PASS"
        and generated.get("validator_result") == "PASS"
        and public_validation.get("status") == "PASS"
        and int(probe.get("video_stream_count") or 0) >= 1
        and int(probe.get("audio_stream_count") or 0) >= 1
    ) else "BLOCKED"
    return {
        "source_id": source_id,
        "account_id": account_id,
        "platform": platform,
        "canonical_url": post.canonical_post_url,
        "source_handle": item.get("source_handle"),
        "local_file": str(path or ""),
        "actual_video_bytes": path.stat().st_size if path and path.is_file() else 0,
        "probe": probe,
        "source_validation": "PASS" if not source_errors else "BLOCKED",
        "source_validation_errors": source_errors,
        "provenance": provenance,
        "effective_permission": "PASS" if permission["allowed"] else "BLOCKED",
        "permission_reasons": permission["reasons"],
        "content_understanding": understanding["status"],
        "route": route.get("route", ""),
        "persona_generation": generated.get("validator_result", "BLOCKED"),
        "public_validation": public_validation.get("status", "BLOCKED"),
        "public_post_preview": public_text,
        "queue_status": queue_status,
        "publisher_eligible": queue_status in ELIGIBLE_STATUSES,
        "preserve_source": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x-dir", type=Path, default=Path("/tmp"))
    parser.add_argument("--youtube-dir", type=Path, default=Path("/tmp"))
    parser.add_argument("--tiktok-dir", type=Path, default=Path("/tmp"))
    parser.add_argument("--platform", choices=["all", "x", "youtube", "tiktok"], default="all")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "config/physical_media_goldens.json").read_text(encoding="utf-8"))
    permissions = _permission_rows(args.use_sheets)
    groups = {
        "x": manifest["x_exact_statuses"],
        "youtube": manifest["youtube_goldens"],
        "tiktok": manifest.get("tiktok_goldens", []),
    }
    items = [
        item
        for platform, platform_items in groups.items()
        if args.platform in {"all", platform}
        for item in platform_items
    ]
    directories = [args.x_dir, args.youtube_dir, args.tiktok_dir]
    rows = [
        verify_item(
            item,
            _find_file(item, directories),
            _find_metadata(item, directories),
            permissions,
        )
        for item in items
    ]
    result = {
        "status": "PASS" if rows and all(row["queue_status"] == "WAITING_REVIEW" for row in rows) else "BLOCKED",
        "golden_count": len(rows),
        "waiting_review_count": sum(row["queue_status"] == "WAITING_REVIEW" for row in rows),
        "rows": rows,
        "production_writes": False,
        "sns_publish": False,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
