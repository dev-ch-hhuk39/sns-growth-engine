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


def build_upload_plan(args: argparse.Namespace, assets: list[dict[str, Any]]) -> dict[str, Any]:
    missing_local = [a for a in assets if not a.get("local_path")]
    if missing_local:
        return {
            "status": "BLOCKED",
            "adapter_status": {"cloudinary": "installed" if importlib.util.find_spec("cloudinary") else "not_installed"},
            "blocked_reasons": ["cut_media_local_path_required"],
            "upload": bool(args.upload),
            "confirm_upload": bool(args.confirm_upload),
        }
    third_party = [
        a for a in assets
        if not rights_allows_media_use(a.get("rights_status", "third_party_reference_only"))
    ]
    if third_party:
        return {
            "status": "BLOCKED",
            "adapter_status": {"cloudinary": "installed" if importlib.util.find_spec("cloudinary") else "not_installed"},
            "blocked_reasons": [
                build_rights_decision(a.get("rights_status", "third_party_reference_only"), action="uploaded").reason
                for a in third_party[:5]
            ],
            "third_party_count": len(third_party),
            "upload": bool(args.upload),
            "confirm_upload": bool(args.confirm_upload),
        }
    result = plan_cloudinary_uploads(
        assets,
        upload=args.upload,
        confirm_upload=args.confirm_upload,
        dry_run=args.dry_run,
    )
    result["adapter_status"] = {"cloudinary": "installed" if importlib.util.find_spec("cloudinary") else "not_installed"}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="upload media assets")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=True)
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
    print(f"[upload_media_assets] account={args.account_id} status={result['status']}")
    print(f"  dry_run={args.dry_run} upload={args.upload} confirm_upload={args.confirm_upload}")
    print(f"  ALLOW_CLOUDINARY_UPLOAD={os.environ.get('ALLOW_CLOUDINARY_UPLOAD', '').lower() == 'true'}")
    for reason in result.get("blocked_reasons", [])[:8]:
        print(f"  [BLOCKED] {reason}")
    print(json.dumps({"status": result["status"], "adapter_status": result.get("adapter_status", {}), "blocked_reasons": result.get("blocked_reasons", [])}, ensure_ascii=False))
    print("  実uploadは実行していません")
    if args.upload and not args.confirm_upload:
        return 1
    return 0 if result["status"] in {"DRY_RUN", "BLOCKED", "READY"} else 1


if __name__ == "__main__":
    sys.exit(main())
