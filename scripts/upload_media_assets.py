#!/usr/bin/env python3
"""Plan Cloudinary uploads; real upload requires env and --confirm-upload."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.cloudinary_uploader import plan_cloudinary_uploads
from media.rights_policy import build_rights_decision, rights_allows_media_use


def _load_json_rows(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    candidate = Path(path)
    if not candidate.exists():
        return []
    return json.loads(candidate.read_text(encoding="utf-8"))


def _asset_from_clip_candidate(args: argparse.Namespace) -> dict[str, Any] | None:
    if not getattr(args, "clip_candidate_id", ""):
        return None
    for row in _load_json_rows(getattr(args, "clip_candidates_json", "")):
        if str(row.get("clip_candidate_id") or row.get("clip_id")) == str(args.clip_candidate_id):
            return {
                "media_asset_id": args.media_asset_id or f"ma_{row.get('clip_candidate_id')}",
                "account_id": row.get("account_id", args.account_id),
                "local_path": row.get("local_clip_path") or row.get("local_path") or "",
                "status": "APPROVED" if row.get("cut_status") in {"CUT", "DONE"} else "WAITING_REVIEW",
                "rights_status": row.get("rights_status", args.rights_status),
                "clip_candidate_id": row.get("clip_candidate_id") or row.get("clip_id"),
            }
    return {
        "media_asset_id": args.media_asset_id or "",
        "account_id": args.account_id,
        "local_path": "",
        "status": "WAITING_REVIEW",
        "rights_status": args.rights_status,
        "clip_candidate_id": args.clip_candidate_id,
        "blocked_reason": "clip_candidate_id_not_found",
    }


def _already_uploaded(asset: dict[str, Any]) -> bool:
    url = str(asset.get("cloudinary_url") or asset.get("storage_url") or "").strip()
    return str(asset.get("upload_status", "")).upper() == "UPLOADED" and url.startswith("https://")


def build_upload_plan(args: argparse.Namespace, assets: list[dict[str, Any]]) -> dict[str, Any]:
    already_uploaded = [a for a in assets if _already_uploaded(a)]
    pending_assets = [a for a in assets if not _already_uploaded(a)]
    missing_local = [a for a in pending_assets if not a.get("local_path")]
    third_party = [
        a for a in assets
        if not rights_allows_media_use(a.get("rights_status", "third_party_reference_only"))
    ]
    result = plan_cloudinary_uploads(
        pending_assets,
        upload=args.upload,
        confirm_upload=args.confirm_upload,
        dry_run=args.dry_run,
    )
    extra_blocked = []
    if missing_local:
        extra_blocked.append("cut_media_local_path_required")
    extra_blocked.extend(
        build_rights_decision(a.get("rights_status", "third_party_reference_only"), action="uploaded").reason
        for a in third_party[:5]
    )
    if extra_blocked:
        result["blocked_reasons"] = list(dict.fromkeys([*result.get("blocked_reasons", []), *extra_blocked]))
        result["status"] = "BLOCKED"
        result["third_party_count"] = len(third_party)
    elif already_uploaded and not pending_assets:
        result["status"] = "ALREADY_UPLOADED"
    result["adapter_status"] = {"cloudinary": "installed" if importlib.util.find_spec("cloudinary") else "not_installed"}
    result["assets"] = pending_assets
    result["already_uploaded_assets"] = already_uploaded
    result["already_uploaded_count"] = len(already_uploaded)
    return result


def execute_cloudinary_uploads(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("status") != "READY":
        return plan
    if importlib.util.find_spec("cloudinary") is None:
        return {**plan, "status": "FAILED", "blocked_reasons": ["cloudinary_not_installed"]}
    try:
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
            api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
            api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
            secure=True,
        )
        if not all(os.environ.get(k) for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")):
            return {**plan, "status": "FAILED", "blocked_reasons": ["cloudinary_credentials_missing"]}
        uploaded = list(plan.get("already_uploaded_assets", []))
        newly_uploaded = 0
        for asset in plan.get("assets", []):
            media_id = str(asset.get("media_asset_id") or Path(str(asset.get("local_path", ""))).stem)
            response = cloudinary.uploader.upload(
                str(asset["local_path"]),
                resource_type="video",
                folder=f"sns-growth-engine/{asset.get('account_id', 'liver_manager')}",
                public_id=media_id,
                overwrite=False,
                unique_filename=False,
            )
            secure_url = str(response.get("secure_url") or "")
            if not secure_url:
                raise RuntimeError("cloudinary_secure_url_missing")
            uploaded.append({
                **asset,
                "cloudinary_url": secure_url,
                "storage_url": secure_url,
                "cloudinary_public_id": str(response.get("public_id") or ""),
                "upload_status": "UPLOADED",
            })
            newly_uploaded += 1
        return {
            **plan,
            "status": "UPLOADED",
            "uploaded_count": len(uploaded),
            "newly_uploaded_count": newly_uploaded,
            "uploaded_assets": uploaded,
            "blocked_reasons": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {**plan, "status": "FAILED", "uploaded_count": 0, "blocked_reasons": [f"{type(exc).__name__}: cloudinary_upload_failed"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="upload media assets")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--confirm-upload", action="store_true")
    parser.add_argument("--rights-status", default="third_party_reference_only")
    parser.add_argument("--local-path", default="clips/mock.mp4")
    parser.add_argument("--clip-candidate-id", default="")
    parser.add_argument("--clip-candidates-json", default="")
    parser.add_argument("--media-asset-id", default="")
    args = parser.parse_args()

    clip_asset = _asset_from_clip_candidate(args)
    assets = [clip_asset] if clip_asset else [{
        "media_asset_id": args.media_asset_id or "mock_media_asset_001",
        "account_id": args.account_id,
        "local_path": args.local_path,
        "status": "APPROVED",
        "rights_status": args.rights_status,
    }]
    result = build_upload_plan(args, assets)
    if args.upload and args.confirm_upload and not args.dry_run and result.get("status") == "READY":
        result = execute_cloudinary_uploads(result)
    print(f"[upload_media_assets] account={args.account_id} status={result['status']}")
    print(f"  dry_run={args.dry_run} upload={args.upload} confirm_upload={args.confirm_upload}")
    print(f"  ALLOW_CLOUDINARY_UPLOAD={os.environ.get('ALLOW_CLOUDINARY_UPLOAD', '').lower() == 'true'}")
    for reason in result.get("blocked_reasons", [])[:8]:
        print(f"  [BLOCKED] {reason}")
    print(json.dumps({
        "status": result["status"],
        "adapter_status": result.get("adapter_status", {}),
        "blocked_reasons": result.get("blocked_reasons", []),
        "uploaded_count": result.get("uploaded_count", 0),
        "already_uploaded_count": result.get("already_uploaded_count", 0),
        "media_asset_ids": [a.get("media_asset_id", "") for a in result.get("uploaded_assets", [])],
    }, ensure_ascii=False))
    if args.upload and not args.confirm_upload:
        return 1
    return 0 if result["status"] in {"DRY_RUN", "BLOCKED", "READY", "UPLOADED", "ALREADY_UPLOADED"} else 1


if __name__ == "__main__":
    sys.exit(main())
