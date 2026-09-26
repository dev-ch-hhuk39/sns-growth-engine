#!/usr/bin/env python3
"""Plan/download approved individual video URLs only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import build_rights_decision  # noqa: E402
from media.media_probe import probe_video_file  # noqa: E402
from media.permission_ledger import evaluate_permission, truthy  # noqa: E402
from acquisition.ytdlp_runtime import physical_download_option_attempts  # noqa: E402
from discover_approved_source_videos import load_existing_source_videos  # noqa: E402
from media_growth_schemas import extract_video_id  # noqa: E402

CLIP_PERMISSION_FLAGS = (
    "allow_download", "allow_cloudinary_storage", "allow_analysis", "allow_cut",
    "allow_clip_repost", "allow_new_caption", "allow_edit",
)



def is_individual_video_url(url: str) -> bool:
    parts = urlsplit(str(url or ""))
    host = parts.netloc.lower()
    path = parts.path
    if "tiktok.com" in host:
        return "/video/" in path
    if "youtube.com" in host:
        return path == "/watch" and bool(parts.query)
    if "youtu.be" in host:
        return len(path.strip("/")) > 0
    return False


def is_approved_storage_url(url: str) -> bool:
    try:
        parts = urlsplit(str(url or ""))
        return (
            parts.scheme == "https" and parts.hostname == "res.cloudinary.com"
            and not parts.username and not parts.password and parts.port in (None, 443)
            and bool(parts.path) and not parts.fragment
        )
    except ValueError:
        return False


def _sha256(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.removeprefix("sha256:")
    return text if re.fullmatch(r"[0-9a-f]{64}", text) else ""


def _same_duration(expected: object, actual: object) -> bool:
    try:
        left, right = float(expected), float(actual)
        return math.isfinite(left) and math.isfinite(right) and min(left, right) > 0 and abs(left - right) <= 1
    except (ValueError, TypeError):
        return False


def _registered_source_matches_video(video: dict, registered: dict) -> bool:
    source_id = str(video.get("source_id") or "")
    account_id = str(video.get("account_id") or "")
    platform = str(video.get("platform") or "").strip().lower()
    video_url = str(video.get("canonical_video_url") or "")
    targets = registered.get("target_account_ids") or [registered.get("target_account_id")]
    if (
        not source_id or registered.get("source_id") != source_id
        or not registered.get("active") or account_id not in {str(value) for value in targets if value}
        or str(registered.get("source_platform") or registered.get("platform") or "").lower() != platform
        or not is_individual_video_url(video_url)
        or not registered.get("media_pipeline_eligible") or not registered.get("clip_enabled")
        or str(registered.get("media_usage_mode") or "").lower() not in {"direct_and_clip", "clip_only"}
    ):
        return False
    registered_url = str(registered.get("canonical_url") or registered.get("source_url") or "")
    registered_handle = str(registered.get("source_handle") or "").strip().lstrip("@").lower()
    rights = str(registered.get("rights_status") or registered.get("rights_policy") or "").lower()
    reuse_policy = str(registered.get("reuse_policy") or "").lower()
    if rights not in {"owned", "licensed", "approved_creator_clip"} or reuse_policy != "approved_creator_clip":
        return False
    try:
        allowed_ids = set(json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8")).get("allowed_source_ids", []))
    except (OSError, ValueError, TypeError):
        return False
    if source_id not in allowed_ids:
        return False
    if platform == "tiktok":
        video_match = re.search(r"/@([^/]+)/video/(\d+)$", urlsplit(video_url).path, re.I)
        source_match = re.search(r"/@([^/?#]+)(?:/|$)", urlsplit(registered_url).path, re.I)
        if not video_match or not source_match:
            return False
        expected = registered_handle or source_match.group(1).lower()
        return video_match.group(1).lower() == expected == source_match.group(1).lower()
    if platform == "youtube":
        video_id = extract_video_id(video_url, platform)
        channel_match = re.search(r"/channel/([^/?#]+)", registered_url, re.I)
        channel_id = registered_handle or (channel_match.group(1) if channel_match else "")
        author = str(video.get("author_handle") or "").strip().lstrip("@").lower()
        return bool(video_id and len(video_id) == 11 and channel_id and author == channel_id.lower())
    return False


def select_stored_full_source(
    source_video_row: dict, source_posts: list[dict], source_post_media: list[dict],
    media_assets: list[dict], media_permissions_rows: list[dict], registered_source: dict | None = None,
) -> dict:
    """Select exactly one full original from snapshots; never perform I/O.

    Direct child provenance, single-video parent, original acquisition backend,
    and full duration are required even when an asset supplies the storage URL.
    A derivative asset alone is never evidence of an original source video.
    """
    video = source_video_row
    url = str(video.get("canonical_video_url") or "")
    source_id = str(video.get("source_id") or "")
    account = str(video.get("account_id") or "")
    registered_source = registered_source or {}
    reasons = []
    if not all((url, source_id, account)) or not _registered_source_matches_video(video, registered_source):
        reasons.append("stored_source_identity_missing")
    permission = evaluate_permission(
        media_permissions_rows, source_id, account_id=account,
        source_handle=str(registered_source.get("source_handle") or "").strip().lstrip("@"),
        required_flags=CLIP_PERMISSION_FLAGS,
    )
    reasons.extend(permission["reasons"])
    if str(permission["row"].get("account_id") or "") != account:
        reasons.append("stored_source_permission_account_mismatch")
    if reasons:
        return {"allowed": False, "blocked_reasons": reasons}

    candidates = []
    video_id = extract_video_id(url, str(video.get("platform") or ""))
    platform = str(video.get("platform") or "").lower()
    expected_handle = str(registered_source.get("source_handle") or "").strip().lstrip("@").lower()
    for post in source_posts:
        post_author = str(post.get("author_handle") or "").strip().lstrip("@").lower()
        video_author = str(video.get("author_handle") or "").strip().lstrip("@").lower()
        author_matches = post_author in ({"", expected_handle, video_author} if platform == "tiktok" else {expected_handle, video_author})
        if not (
            post.get("canonical_post_url") == url and post.get("source_id") == source_id
            and post.get("target_account_id") == account and post.get("source_post_id")
            and extract_video_id(str(post.get("canonical_post_url") or ""), platform) == video_id
            and author_matches
            and str(post.get("media_count")) == "1"
            and str(post.get("rights_status") or "").lower() in {"owned", "licensed", "approved_creator_clip"}
            and str(post.get("permission_status") or "").lower() == "approved"
        ):
            continue
        for media in source_post_media:
            if not (
                media.get("source_post_id") == post["source_post_id"]
                and media.get("canonical_post_url") == url and media.get("source_post_media_id")
                and media.get("media_type") == "video"
                and is_individual_video_url(str(media.get("original_media_url") or url))
                and str(media.get("resolver_backend") or "").lower() in {
                    "yt_dlp", "tiktok_public_embed", "tiktok_public_embed_direct_http",
                    "public_embed_direct_http", "threads_public_http_refreshed_direct_http",
                }
                and str(media.get("media_index") or "") == "0"
                and str(media.get("rights_status") or "").lower() in {"owned", "licensed", "approved_creator_clip"}
                and str(media.get("permission_status") or "").lower() == "approved"
                and _same_duration(video.get("duration_seconds"), media.get("duration_seconds"))
            ):
                continue
            asset_id = media.get("media_asset_id") or media.get("media_id")
            linked = [a for a in media_assets if a.get("media_id") == asset_id] if asset_id else []
            if len(linked) != 1:
                continue
            asset = linked[0]
            rows = [video, post, media, asset]
            if any(
                row.get("clip_candidate_id") or row.get("parent_media_asset_id")
                or truthy(row.get("is_derivative"))
                or any(row.get(key) not in (None, "") for key in ("start_seconds", "end_seconds"))
                or str(row.get("media_role") or "full_source") != "full_source"
                for row in rows
            ):
                continue
            if any(not build_rights_decision(row.get("rights_status"), "download").allowed
                   or str(row.get("permission_status") or "").lower() != "approved" for row in rows):
                continue
            if asset and not (
                asset.get("account_id") == account and asset.get("reference_post_id") == post["source_post_id"]
                and asset.get("source_post_url") == url and asset.get("media_type") == "video"
                and str(asset.get("upload_status")).upper() == "UPLOADED"
                and _same_duration(video.get("duration_seconds"), asset.get("duration_seconds"))
            ):
                continue
            digest = _sha256(media.get("content_hash"))
            video_digest = _sha256(video.get("content_hash"))
            storage = str(media.get("storage_url") or asset.get("storage_url") or "")
            if not digest or digest != video_digest or not is_approved_storage_url(storage):
                continue
            asset_digest = _sha256(asset.get("content_hash")) if asset else ""
            if asset and ((asset_digest and asset_digest != digest) or asset.get("storage_url") != storage):
                continue
            if asset and str(asset.get("cloudinary_public_id") or "") and str(media.get("cloudinary_public_id") or "") and asset.get("cloudinary_public_id") != media.get("cloudinary_public_id"):
                continue
            if str(media.get("cloudinary_status")).upper() != "UPLOADED":
                continue
            candidates.append({"storage_url": storage, "content_hash": digest,
                               "source_post_id": post["source_post_id"],
                               "source_post_media_id": media["source_post_media_id"],
                               "media_asset_id": str(asset.get("media_id") or ""),
                               "duration_seconds": video["duration_seconds"]})
    if len(candidates) != 1:
        return {"allowed": False, "blocked_reasons": ["stored_full_source_missing_or_ambiguous"]}
    return {"allowed": True, "blocked_reasons": [], **candidates[0]}


def _resolve_source_video(args: argparse.Namespace) -> dict:
    injected = getattr(args, "source_video_row", None)
    if isinstance(injected, dict):
        return dict(injected)
    if not getattr(args, "source_video_id", ""):
        return {}
    for row in load_existing_source_videos(getattr(args, "source_videos_json", "")):
        if str(row.get("source_video_id", "")) == str(args.source_video_id):
            return dict(row)
    return {}


def _verified_existing_download(source_video: dict) -> dict:
    if str(source_video.get("download_status", "")).upper() != "DOWNLOADED":
        return {}
    local_path = str(source_video.get("local_path", "")).strip()
    if not local_path:
        return {}
    local = Path(local_path)
    if not local.is_file():
        return {}
    media_probe = probe_video_file(local)
    if media_probe.get("media_probe_status") != "PASS":
        return {}
    source_video_id = str(source_video.get("source_video_id") or "video")
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_video_id)[:120]
    return {
        "status": "DOWNLOADED",
        "media_asset_id": f"download_{safe_id}",
        "local_path": str(local),
        "file_size_bytes": local.stat().st_size,
        "reused_existing_download": True,
        **media_probe,
    }


def build_download_plan(args: argparse.Namespace) -> dict:
    source_video = _resolve_source_video(args)
    canonical_source_url = source_video.get("canonical_video_url") or args.source_url
    approved_storage_url = source_video.get("approved_storage_url") or ""
    source_url = approved_storage_url or canonical_source_url
    rights_status = source_video.get("rights_status") or args.rights_status
    decision = build_rights_decision(rights_status, action="download")
    allow_env = os.environ.get("ALLOW_VIDEO_DOWNLOAD", "").lower() == "true"
    existing_download = _verified_existing_download(source_video)
    blocked = []
    permission_rows = getattr(args, "media_permissions_rows", None)
    registered_source = getattr(args, "registered_source_row", None) or {}
    if permission_rows is not None:
        if not _registered_source_matches_video(source_video, registered_source):
            blocked.append("registered_source_identity_mismatch")
        ledger = evaluate_permission(
            permission_rows,
            str(source_video.get("source_id") or ""),
            account_id=str(source_video.get("account_id") or ""),
            source_handle=str(registered_source.get("source_handle") or "").strip().lstrip("@"),
            required_flags=CLIP_PERMISSION_FLAGS,
        )
        blocked.extend(ledger["reasons"])
        if str(ledger["row"].get("account_id") or "") != str(source_video.get("account_id") or ""):
            blocked.append("permission_account_scope_mismatch")
    stored_only = bool(getattr(args, "stored_source_only", False))
    stored_requested = stored_only or getattr(args, "source_media_row", None) is not None
    stored = {}
    if stored_requested:
        stored = select_stored_full_source(
            source_video, [getattr(args, "source_post_row", None) or {}],
            [getattr(args, "source_media_row", None) or {}],
            getattr(args, "media_assets_rows", None) or [],
            permission_rows or [],
            registered_source,
        )
        blocked.extend(stored["blocked_reasons"])
        source_url = stored.get("storage_url", "")
        # Legacy cached files have no verified byte identity; re-fetch storage.
        existing_download = {}
    if getattr(args, "source_video_id", "") and not source_video:
        blocked.append("source_video_id_not_found")
    if not decision.allowed:
        blocked.append(decision.reason)
    if not is_individual_video_url(canonical_source_url):
        blocked.append("individual_video_url_required")
    if approved_storage_url and not is_approved_storage_url(approved_storage_url):
        blocked.append("approved_storage_url_invalid")
    if args.download and not args.confirm_download:
        blocked.append("--download requires --confirm-download")
    if args.download and not allow_env:
        blocked.append("ALLOW_VIDEO_DOWNLOAD=true is required")
    reused = bool(args.download and not blocked and existing_download)
    status = (
        "DOWNLOADED" if reused
        else "READY" if args.download and not blocked
        else "BLOCKED" if blocked
        else "PLAN_ONLY"
    )
    return {
        "status": status,
        "source_video_id": getattr(args, "source_video_id", ""),
        "source_url": source_url,
        "stored_source_only": stored_only,
        "stored_source": stored,
        "rights_status": decision.rights_status,
        "rights_decision": decision.as_dict(),
        "adapter_status": {"yt_dlp": "installed" if importlib.util.find_spec("yt_dlp") else "not_installed"},
        "output_dir": str(Path(os.environ.get("SNS_MEDIA_PREP_WORKSPACE", ROOT / "output")) / "downloads"),
        "download": bool(args.download),
        "confirm_download": bool(args.confirm_download),
        "allow_video_download": allow_env,
        "would_download": bool(args.download and not blocked and not reused),
        "blocked_reasons": blocked,
        "download_result": existing_download if reused else {
            "media_asset_id": "",
            "local_path": "",
            "status": "NOT_DOWNLOADED",
        },
    }


def execute_download(plan: dict) -> dict:
    """Download one approved individual video. Secrets/cookies are never accepted or logged."""
    if plan.get("stored_source_only") or plan.get("stored_source"):
        if plan.get("status") != "READY" or not plan.get("would_download"):
            return plan
        return _execute_stored_download(plan)
    if (
        plan.get("status") == "DOWNLOADED"
        and plan.get("download_result", {}).get("status") == "DOWNLOADED"
    ):
        return plan
    if plan.get("status") != "READY" or not plan.get("would_download"):
        return {**plan, "download_result": {"status": "NOT_DOWNLOADED", "media_asset_id": "", "local_path": ""}}
    if importlib.util.find_spec("yt_dlp") is None:
        return {**plan, "status": "FAILED", "blocked_reasons": ["yt_dlp_not_installed"]}
    import yt_dlp  # type: ignore[import]

    source_video_id = str(plan.get("source_video_id") or "video")
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_video_id)[:120]
    output_dir = Path(str(plan["output_dir"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / f"{safe_id}.%(ext)s")

    # GitHub runners and local retries may retain an older partial output.
    # Never let glob ordering select a stale audio-only .mp4.
    for stale in output_dir.glob(f"{safe_id}.*"):
        if stale.is_file():
            stale.unlink()

    platform = "youtube" if "youtu" in str(plan["source_url"]).lower() else "tiktok"
    base_options = {
        "outtmpl": template,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "max_filesize": 300 * 1024 * 1024,
    }
    try:
        last_error: Exception | None = None
        for opts in physical_download_option_attempts(platform, base_options):
            for stale in output_dir.glob(f"{safe_id}.*"):
                if stale.is_file():
                    stale.unlink()
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([str(plan["source_url"])])
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        matches = sorted(
            path
            for path in output_dir.glob(
                f"{safe_id}.*"
            )
            if path.suffix.lower()
            in {
                ".mp4",
                ".mov",
                ".webm",
                ".mkv",
            }
        )

        local = None
        media_probe: dict[str, object] = {}

        for candidate in matches:
            candidate_probe = probe_video_file(
                candidate
            )

            if (
                candidate_probe.get(
                    "media_probe_status"
                )
                == "PASS"
            ):
                local = candidate
                media_probe = candidate_probe
                break

        if local is None:
            raise RuntimeError(
                "downloaded_media_missing_av_streams"
            )
        return {
            **plan,
            "status": "DOWNLOADED",
            "would_download": False,
            "download_result": {
                "status": "DOWNLOADED",
                "media_asset_id": f"download_{safe_id}",
                "local_path": str(local),
                "file_size_bytes": local.stat().st_size,
                **media_probe,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            **plan,
            "status": "FAILED",
            "would_download": False,
            "blocked_reasons": [f"{type(exc).__name__}: download_failed"],
            "download_result": {"status": "FAILED", "media_asset_id": "", "local_path": ""},
        }


class _NoStorageRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("stored_source_redirect_forbidden")


def _execute_stored_download(plan: dict) -> dict:
    local = None
    try:
        stored = plan.get("stored_source") or {}
        if not (
            stored.get("allowed") and not plan.get("blocked_reasons")
            and plan.get("download") and plan.get("confirm_download")
            and os.environ.get("ALLOW_VIDEO_DOWNLOAD", "").lower() == "true"
            and plan.get("rights_decision", {}).get("allowed")
            and plan.get("source_url") == stored.get("storage_url")
            and is_approved_storage_url(stored.get("storage_url"))
            and _sha256(stored.get("content_hash"))
        ):
            raise ValueError("stored_source_execution_gate")
        output = Path(plan["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(dir=output, prefix="stored_source_", suffix=".mp4", delete=False) as target:
            local = Path(target.name)
            with build_opener(_NoStorageRedirects()).open(stored["storage_url"], timeout=30) as response:
                if response.status != 200 or response.geturl() != stored["storage_url"]:
                    raise ValueError("stored_source_response_invalid")
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 300 * 1024 * 1024:
                        raise ValueError("stored_source_size_limit")
                    digest.update(chunk)
                    target.write(chunk)
        if digest.hexdigest() != stored["content_hash"]:
            raise ValueError("stored_source_hash_mismatch")
        probe = probe_video_file(local)
        if probe.get("media_probe_status") != "PASS" or not _same_duration(stored.get("duration_seconds"), probe.get("duration_seconds")):
            raise ValueError("stored_source_video_invalid")
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(plan.get("source_video_id") or "video"))[:120]
        return {**plan, "status": "DOWNLOADED", "would_download": False,
                "download_result": {**probe, "status": "DOWNLOADED", "media_asset_id": f"download_{safe_id}",
                                    "local_path": str(local), "file_size_bytes": size,
                                    "content_hash": digest.hexdigest(), "stored_full_source": True}}
    except Exception as exc:  # noqa: BLE001
        if local is not None:
            local.unlink(missing_ok=True)
        reason = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("stored_source_") else "stored_source_download_failed"
        return {**plan, "status": "FAILED", "would_download": False, "blocked_reasons": [reason],
                "download_result": {"status": "FAILED", "media_asset_id": "", "local_path": ""}}


def main() -> int:
    parser = argparse.ArgumentParser(description="download approved media")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-video-id", default="")
    parser.add_argument("--source-videos-json", default="")
    parser.add_argument("--rights-status", default="third_party_reference_only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--confirm-download", action="store_true")
    parser.add_argument("--stored-source-only", action="store_true")
    args = parser.parse_args()
    if not args.source_url and not args.source_video_id:
        parser.error("--source-url or --source-video-id is required")
    plan = build_download_plan(args)
    if args.download and not args.dry_run and plan["status"] == "READY":
        plan = execute_download(plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["status"] in {"BLOCKED", "FAILED"} and args.download else 0


if __name__ == "__main__":
    raise SystemExit(main())
