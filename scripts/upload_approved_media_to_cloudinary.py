#!/usr/bin/env python3
"""Upload APPROVED / self_generated media to Cloudinary (heavily gated).

安全方針（プロジェクト固有ルールに準拠）:
  - 実 upload は次をすべて満たすときだけ:
      --upload かつ --confirm-upload かつ ALLOW_CLOUDINARY_UPLOAD=true
  - approval_status=APPROVED 以外の media は upload 禁止。
  - 権利が clear（owned/allowed/approved・no_reuse でない・media_reuse_risk≠high・
    rights_review_required≠true・permission_status が approved/not_required）でなければ禁止。
  - ローカルにファイルが無い media は upload しない。
  - secret 値（cloud_name/api_key/api_secret）は一切表示しない。
  - 既定は計画のみ（DRY_RUN）。実 upload は明示フラグが揃ったときだけ。

入力:
  --input-json {"media_assets":[...]} でオフライン計画（credentials不要・テスト可能）。
  --upload 時に --input-json が無ければ本番 Sheets の media_assets を読む。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from media.queue_media_attach import is_media_rights_clear  # noqa: E402

OK_PERMISSION = {"approved", "not_required", ""}


def evaluate_upload_gate(
    asset: dict[str, Any],
    *,
    upload: bool,
    confirm_upload: bool,
    allow_env: bool,
) -> dict[str, Any]:
    """1 件の media_asset に対する upload 可否を判定する（HTTP は行わない）。"""
    blocked: list[str] = []

    approval = str(asset.get("approval_status", "")).strip().upper()
    status = str(asset.get("status", "")).strip().upper()
    # approval_status=APPROVED が原則。self_generated は status で許可。
    approved = approval == "APPROVED" or status == "SELF_GENERATED"
    if not approved:
        blocked.append(f"approval_status != APPROVED (approval_status={approval or '空'} status={status or '空'})")

    if not is_media_rights_clear(asset):
        blocked.append("rights not clear (rights_policy/reuse_policy/media_policy/risk)")

    if str(asset.get("rights_review_required", "")).strip().lower() in {"true", "1", "yes"}:
        blocked.append("rights_review_required=true")
    if str(asset.get("permission_status", "")).strip().lower() not in OK_PERMISSION:
        blocked.append(f"permission_status={asset.get('permission_status')} not approved/not_required")

    local_path = str(asset.get("local_path", "")).strip()
    if not local_path:
        blocked.append("local_path 未設定（upload 対象ファイルが無い）")
    elif not Path(local_path).is_file():
        blocked.append(f"local file not found: {local_path}")

    if upload and not confirm_upload:
        blocked.append("--upload には --confirm-upload が必要")
    if upload and not allow_env:
        blocked.append("ALLOW_CLOUDINARY_UPLOAD=true が必要")
    if not upload:
        blocked.append("upload フラグ未指定: plan only")

    return {
        "media_asset_id": str(asset.get("media_asset_id", "")),
        "approval_status": approval,
        "status": status,
        "allowed": not blocked,
        "blocked_reasons": blocked,
    }


def _real_upload(asset: dict[str, Any]) -> dict[str, Any]:
    """gating を通過した 1 件を実 upload する。secret は表示しない。"""
    from config_loader import get_cloudinary_config
    from media.cloudinary_client import build_public_id, upload_to_cloudinary

    cfg = get_cloudinary_config()
    local_path = Path(str(asset.get("local_path", "")))
    data = local_path.read_bytes()
    suffix = local_path.suffix.lower()
    mime = "video/mp4" if suffix in {".mp4", ".mov"} else f"image/{(suffix.lstrip('.') or 'png')}"
    public_id = build_public_id(
        str(asset.get("media_asset_id", "media")),
        str(asset.get("account_id", "account")),
    )
    secure_url = upload_to_cloudinary(data, mime, public_id, cfg)
    return {"media_asset_id": asset.get("media_asset_id", ""), "cloudinary_url": secure_url}


def _load_assets(input_json: str | None, upload: bool) -> list[dict[str, Any]]:
    if input_json:
        with open(input_json, encoding="utf-8") as f:
            return json.load(f).get("media_assets", [])
    if upload:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        return [dict(r) for r in client._ws("media_assets").get_all_records()]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="upload approved/self_generated media to Cloudinary (gated)")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--input-json", help='{"media_assets":[...]} for offline planning/testing')
    parser.add_argument("--upload", action="store_true", help="attempt real upload (needs --confirm-upload + env)")
    parser.add_argument("--confirm-upload", action="store_true", help="explicit confirmation for real upload")
    parser.add_argument("--max-uploads", type=int, default=1, help="cap real uploads (default 1)")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account は不可"}, ensure_ascii=False))
        return 1

    allow_env = os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "").strip().lower() == "true"
    assets = [a for a in _load_assets(args.input_json, args.upload)
              if str(a.get("account_id", "")) in ("", args.account_id)]

    gates = [evaluate_upload_gate(a, upload=args.upload, confirm_upload=args.confirm_upload, allow_env=allow_env) for a in assets]
    allowed_ids = {g["media_asset_id"] for g in gates if g["allowed"]}

    # 実 upload は gating 通過時のみ。それ以外は計画表示で終了。
    uploaded: list[dict[str, Any]] = []
    if args.upload and args.confirm_upload and allow_env and allowed_ids:
        for asset in assets:
            if asset.get("media_asset_id") in allowed_ids and len(uploaded) < max(1, args.max_uploads):
                uploaded.append(_real_upload(asset))

    status = "UPLOADED" if uploaded else ("BLOCKED" if any(not g["allowed"] for g in gates) else "DRY_RUN")
    print(json.dumps({
        "status": status,
        "account_id": args.account_id,
        "allow_cloudinary_upload": allow_env,
        "asset_count": len(assets),
        "allowed_count": len(allowed_ids),
        "uploaded_count": len(uploaded),
        "gates": gates,
        "uploaded": uploaded,
        "notes": "secret 値は表示していません。実 upload は --upload --confirm-upload かつ ALLOW_CLOUDINARY_UPLOAD=true のときだけ。",
    }, ensure_ascii=False, indent=2))
    return 0 if (uploaded or not args.upload) else 1


if __name__ == "__main__":
    raise SystemExit(main())
