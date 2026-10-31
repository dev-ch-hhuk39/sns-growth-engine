#!/usr/bin/env python3
"""Verify existing local Golden evidence without downloading or analyzing media."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.models import (  # noqa: E402
    NormalizedMediaItem, NormalizedSourcePost, stable_content_hash, validate_source_post,
)
from config_loader import get_config  # noqa: E402
from generation.media_platform_policy import (  # noqa: E402
    OWNER_REFERENCE_ACCOUNTS, can_attempt_physical_media, normalize_platform,
)
from generation.reference_first_router import choose_reference_first_route  # noqa: E402
from generation.video_clip_materializer import probe_media_streams  # noqa: E402
from generation_quality_gates import evaluate_generation_quality  # noqa: E402
from media.golden_evidence import (  # noqa: E402
    validate_metadata_provenance, validate_registered_binding, validate_semantic_evidence,
)
from media.permission_ledger import (  # noqa: E402
    _targets, account_source_permission_reasons, evaluate_permission,
)
from public_post_quality import final_public_post_validator, generate_production_post  # noqa: E402
from reference.source_registry import load_registry  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402

MAX_JSON_BYTES = 2 * 1024**2
MAX_VIDEO_BYTES = 2 * 1024**3
MAX_DIRECTORY_FILES = 1000


def _identity(path: Path) -> tuple[int, int, int, int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("regular_unlinked_artifact_required")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _open_verified(path: Path, limit: int):
    before = _identity(path)
    if not 0 < before[2] <= limit:
        raise ValueError("artifact_size_limit")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    stream = os.fdopen(fd, "rb")
    info = os.fstat(stream.fileno())
    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != before:
        stream.close()
        raise ValueError("artifact_changed")
    return stream, before


def _read_json(path: Path) -> dict[str, Any]:
    stream, before = _open_verified(path, MAX_JSON_BYTES)
    with stream:
        payload = json.loads(stream.read(MAX_JSON_BYTES + 1))
    if _identity(path) != before or not isinstance(payload, dict):
        raise ValueError("invalid_json_artifact")
    return payload


def _hash_video(path: Path) -> str:
    stream, before = _open_verified(path, MAX_VIDEO_BYTES)
    digest, total = hashlib.sha256(), 0
    with stream:
        while chunk := stream.read(1024**2):
            total += len(chunk)
            if total > MAX_VIDEO_BYTES:
                raise ValueError("video_size_limit")
            digest.update(chunk)
    if _identity(path) != before or total != before[2]:
        raise ValueError("artifact_changed")
    return digest.hexdigest()


def select_artifact(binding: dict[str, Any], directories: list[Path]) -> dict[str, Any]:
    """Select a unique exact post and its same-basename extracted metadata."""
    token = re.compile(r"(?<![A-Za-z0-9])" + re.escape(binding["external_post_id"]) + r"(?![A-Za-z0-9])")
    candidates, inspected = [], set()
    try:
        for directory in directories:
            if directory in inspected:
                continue
            inspected.add(directory)
            if directory.is_symlink() or not directory.is_dir():
                continue
            entries = []
            for path in directory.iterdir():
                entries.append(path)
                if len(entries) > MAX_DIRECTORY_FILES:
                    raise ValueError("artifact_directory_limit")
            for path in sorted(entries):
                if path.suffix != ".mp4" or not token.search(path.stem):
                    continue
                _identity(path)
                metadata_path = path.with_suffix(".info.json")
                metadata = _read_json(metadata_path)
                provenance = validate_metadata_provenance(binding, metadata)
                if provenance["status"] == "PASS":
                    candidates.append((path, metadata_path, metadata, provenance))
    except (OSError, ValueError, TypeError):
        return {"status": "BLOCKED", "reasons": ["artifact_pair_unverified"]}
    if len(candidates) != 1:
        return {"status": "BLOCKED", "reasons": ["artifact_pair_missing_or_ambiguous"]}
    path, metadata_path, metadata, provenance = candidates[0]
    return {"status": "PASS", "reasons": [], "path": path,
            "metadata_path": metadata_path, "metadata": metadata, "provenance": provenance}


def _permission_rows(use_sheets: bool) -> list[dict[str, Any]]:
    if not use_sheets:
        return []
    cfg = get_config()
    if cfg.get("dry_run") or str(os.environ.get("MOCK_SHEETS", "")).strip().lower() in {"1", "true", "yes"}:
        raise ValueError("real_permission_client_required")
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    if type(client) is not SheetsClient or client.dry_run is not False:
        raise ValueError("real_permission_client_required")
    return [dict(row) for row in read_records_safely(client, "media_permissions", preserve_strings=True)]


def verify_owner_goldens(directories: dict[str, Path] | None = None) -> dict[str, Any]:
    """Explicit current X/YouTube verification; absent directories stay offline.

    This reads existing artifacts and the live ledger only. It never downloads,
    analyzes with a provider, writes Sheets, uploads or authorizes publishing.
    Historical A/V declarations and caller-supplied reports are not inputs.
    """
    result: dict[str, Any] = {
        "status": "NOT_RUN", "reasons": ["current_owner_physical_verification_not_requested"],
        "checks": [], "provider_calls": 0, "production_writes": False,
        "publish_authorized": False, "overall_goal_acceptance": False,
    }
    if directories is None:
        return result
    result.update(status="BLOCKED", reasons=["physical_artifact_directories_unverified"])
    if set(directories) != {"x", "youtube"}:
        return result
    try:
        paths = {platform: Path(value) for platform, value in directories.items()}
        if any(not path.is_absolute() or not path.is_dir() or path.resolve(strict=True) != path
               for path in paths.values()):
            return result
        manifest = json.loads((ROOT / "config/physical_media_goldens.json").read_text(encoding="utf-8"))
        items = [(platform, dict(item)) for platform, key in (
            ("x", "x_exact_statuses"), ("youtube", "youtube_goldens")) for item in manifest[key]]
        if not 4 <= len(items) <= 20:
            raise ValueError("manifest_bound")
        registry = load_registry(preserve_duplicates=True)
        coverage, seen, bindings = set(), set(), []
        for platform, item in items:
            account = item.get("account_id")
            decision = validate_registered_binding(item, registry)
            if (account not in OWNER_REFERENCE_ACCOUNTS or decision["status"] != "PASS"
                    or decision["binding"]["platform"] != platform):
                raise ValueError("manifest_binding")
            binding = decision["binding"]
            identity = (account, binding["canonical_url"])
            if identity in seen:
                raise ValueError("manifest_duplicate")
            seen.add(identity)
            coverage.add((account, platform))
            bindings.append(binding)
            if select_artifact(binding, [paths[platform]])["status"] != "PASS":
                return result
        if coverage != {(account, platform) for account in OWNER_REFERENCE_ACCOUNTS for platform in paths}:
            raise ValueError("manifest_coverage")
    except (OSError, ValueError, TypeError, KeyError):
        result["reasons"] = ["current_owner_manifest_or_artifacts_unverified"]
        return result
    try:
        permissions = _permission_rows(True)
        rows = [verify_item(item, None, {}, permissions, registry_rows=registry,
                            directories=[paths[platform]]) for platform, item in items]
        # Re-read without invocation caches after all bounded local byte/probe
        # work. A later revoke/read failure must invalidate the earlier result.
        current_permissions = _permission_rows(True)
        checks = []
        for (platform, item), binding, row in zip(items, bindings, rows):
            permission = evaluate_permission(current_permissions, item["source_id"],
                account_id=item["account_id"], source_handle=binding["source_handle"],
                required_flags=("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption"))
            scope_reasons = account_source_permission_reasons(permission["row"],
                account_id=item["account_id"], source_handle=binding["source_handle"])
            passed = (row.get("queue_status") == "WAITING_REVIEW"
                      and row.get("publisher_eligible") is False
                      and row.get("preserve_source") is True
                      and all(row.get(key) == "PASS" for key in (
                          "registered_source", "artifact_binding", "technical_bytes", "content_understanding",
                          "effective_permission", "source_validation", "persona_generation", "generation_quality",
                          "media_text_quality", "public_validation"))
                      and permission["allowed"] and not scope_reasons)
            checks.append({"account_id": item["account_id"], "platform": platform,
                           "source_id": item["source_id"], "status": "PASS" if passed else "BLOCKED"})
        passed = all(row["status"] == "PASS" for row in checks)
        result.update(status="PASS" if passed else "BLOCKED", checks=checks,
                      reasons=[] if passed else ["current_owner_physical_evidence_incomplete"],
                      verified_at=datetime.now(timezone.utc).isoformat(),
                      permission_authority="live_media_permissions_two_uncached_reads")
    except Exception:
        # Provider exception text and unpublished previews are private.
        result.update(status="BLOCKED", reasons=["current_owner_physical_verification_unavailable"])
    return result


def verify_item(item: dict[str, Any], path: Path | None, metadata: dict[str, Any],
                permissions: list[dict[str, Any]], *, registry_rows: list[dict[str, Any]] | None = None,
                directories: list[Path] | None = None) -> dict[str, Any]:
    account_id, source_id, url = (str(item.get(k) or "") for k in ("account_id", "source_id", "url"))
    platform = normalize_platform(item.get("platform", ""), url)
    result: dict[str, Any] = {
        "source_id": source_id, "account_id": account_id, "platform": platform,
        "canonical_url": url, "actual_video_bytes": 0, "artifact_binding": "NOT_CHECKED",
        "technical_bytes": "NOT_CHECKED", "content_understanding": "NOT_CHECKED",
        "effective_permission": "NOT_CHECKED", "source_validation": "NOT_CHECKED",
        "queue_status": "BLOCKED", "publisher_eligible": False, "preserve_source": True,
    }
    if account_id in OWNER_REFERENCE_ACCOUNTS and not can_attempt_physical_media(platform, url, account_id=account_id):
        result["reason"] = f"physical_media_platform_deferred:{platform or 'unknown'}"
        return result
    registered = validate_registered_binding(item, load_registry(preserve_duplicates=True) if registry_rows is None else registry_rows)
    result["registered_source"] = registered["status"]
    if registered["status"] != "PASS":
        result["reasons"] = registered["reasons"]
        return result
    binding = registered["binding"]
    bundle = select_artifact(binding, directories if directories is not None else ([path.parent] if path else []))
    result["artifact_binding"] = bundle["status"]
    if bundle["status"] != "PASS":
        result["reasons"] = bundle["reasons"]
        return result
    actual_path = bundle["path"]
    if (path is not None and path != actual_path) or (metadata and metadata != bundle["metadata"]):
        result.update(artifact_binding="BLOCKED", reasons=["caller_artifact_mismatch"])
        return result
    metadata = bundle["metadata"]
    result.update(provenance=bundle["provenance"], local_file=str(actual_path))
    try:
        snapshots = {p: _identity(p) for p in (actual_path, bundle["metadata_path"])}
        if _read_json(bundle["metadata_path"]) != metadata:
            raise ValueError("metadata_changed")
        digest = _hash_video(actual_path)
        probe = probe_media_streams(actual_path, timeout_seconds=30)
        technical_ok = (int(probe.get("video_stream_count") or 0) >= 1
                        and int(probe.get("audio_stream_count") or 0) >= 1
                        and int(probe.get("width") or 0) > 0 and int(probe.get("height") or 0) > 0
                        and math.isfinite(float(probe.get("duration_seconds") or 0))
                        and float(probe.get("duration_seconds") or 0) > 0)
        proof_path = actual_path.with_suffix(".understanding.json")
        try:
            snapshots[proof_path] = _identity(proof_path)
            proof = _read_json(proof_path)
        except (OSError, ValueError, TypeError):
            proof = {}
        semantic = validate_semantic_evidence(binding, digest, proof)
        if any(_identity(p) != snapshot for p, snapshot in snapshots.items()):
            raise ValueError("artifact_changed")
    except (OSError, ValueError, TypeError, OverflowError, RuntimeError, subprocess.SubprocessError):
        result.update(technical_bytes="BLOCKED", reasons=["artifact_probe_or_integrity_unverified"])
        return result
    result.update(actual_video_bytes=snapshots[actual_path][2], content_hash=digest, probe=probe,
                  technical_bytes="PASS" if technical_ok else "BLOCKED",
                  content_understanding=semantic["status"], semantic_reasons=semantic["reasons"])
    permission = evaluate_permission(permissions, source_id, account_id=account_id,
        source_handle=binding["source_handle"], required_flags=("allow_download", "allow_cloudinary_storage",
                                                               "allow_original_repost", "allow_new_caption"))
    row = permission["row"]
    if (str(row.get("account_id") or "") != account_id
            or account_id not in _targets(row.get("allowed_accounts") or row.get("account_id"))):
        permission["allowed"] = False
        permission["reasons"].append("permission_explicit_account_binding_required")
    result.update(effective_permission="PASS" if permission["allowed"] else "BLOCKED",
                  permission_reasons=permission["reasons"])
    if not technical_ok or semantic["status"] != "PASS" or not permission["allowed"]:
        return result
    context = semantic["context"]
    source_text = str(metadata.get("description") or "")
    post_id = f"golden_{source_id}_{binding['external_post_id']}"
    media = NormalizedMediaItem(source_post_media_id=f"spm_{post_id}_0", source_post_id=post_id,
        media_index=0, media_type="video", canonical_post_url=binding["canonical_url"],
        original_media_url=binding["canonical_url"], resolver_backend="yt_dlp", mime_type="video/mp4",
        width=str(probe["width"]), height=str(probe["height"]), duration_seconds=str(probe["duration_seconds"]))
    post = NormalizedSourcePost(source_post_id=post_id, source_id=source_id, target_account_id=account_id,
        platform=binding["platform"], profile_url=binding["registered_profile_url"],
        canonical_post_url=binding["canonical_url"], external_post_id=binding["external_post_id"],
        original_post_text=source_text, published_at="", author_handle=binding["source_handle"].lstrip("@"),
        media_items=(media,), collection_backend="yt_dlp", backend_version="physical-golden-evidence-v2",
        content_hash=stable_content_hash(source_text, [binding["canonical_url"]]),
        discovered_at=datetime.now(timezone.utc).isoformat(), detail_status="COMPLETE")
    errors = validate_source_post(post)
    result.update(source_validation="BLOCKED" if errors else "PASS", source_validation_errors=errors)
    route = choose_reference_first_route(desired_route="direct_reference_media",
        source_has_direct_media_permission=True, content_understanding={"status": "PASS",
            "summary": context["visual_summary"], "standalone_segment_confirmed": False, "clip_worthy": False})
    # This shared composer is deterministic and local; no inference provider is called.
    generated = generate_production_post(account_id, batch_id="physical-golden-evidence-v2",
        content_type="reference_text_generation", reference_signal=context["visual_summary"])
    public_text = str(generated.get("public_post_text") or "")
    public_validation = final_public_post_validator(public_text, account_id)
    quality = generated.get("generation_quality")
    quality_ok = isinstance(quality, dict) and quality.get("status") == "PASS" and not generated.get("blocked_reasons")
    alignment = evaluate_generation_quality(account_id, public_text, [], visual_text=context["visual_summary"])
    if (not errors and route.get("status") == "PASS" and generated.get("validator_result") == "PASS"
            and public_validation.get("status") == "PASS" and quality_ok and alignment.get("status") == "PASS"):
        result["queue_status"] = "WAITING_REVIEW"
    result.update(route=route.get("route", ""), persona_generation=generated.get("validator_result", "BLOCKED"),
                  generation_quality="PASS" if quality_ok else "BLOCKED", media_text_quality=alignment.get("status", "BLOCKED"),
                  public_validation=public_validation.get("status", "BLOCKED"), public_post_preview=public_text)
    return result


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
    permissions, registry = _permission_rows(args.use_sheets), load_registry(preserve_duplicates=True)
    groups = {"x": manifest["x_exact_statuses"], "youtube": manifest["youtube_goldens"],
              "tiktok": manifest.get("tiktok_goldens", [])}
    items = [item for platform, group in groups.items() if args.platform in {"all", platform} for item in group]
    directories = [args.x_dir, args.youtube_dir, args.tiktok_dir]
    rows = [verify_item(item, None, {}, permissions, registry_rows=registry, directories=directories) for item in items]
    result = {"status": "PASS" if rows and all(r["queue_status"] == "WAITING_REVIEW" for r in rows) else "BLOCKED",
              "golden_count": len(rows), "waiting_review_count": sum(r["queue_status"] == "WAITING_REVIEW" for r in rows),
              "rows": rows, "production_writes": False, "sns_publish": False,
              "provider_calls": 0, "overall_goal_acceptance": False}
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
