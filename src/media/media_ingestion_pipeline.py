"""
media_ingestion_pipeline.py - メディア取り込みパイプライン（Phase 7.C）

video_url / image_url / local_file → media_assetsへ登録。
Cloudinary upload は ALLOW_CLOUDINARY_UPLOAD=true かつ --confirm-upload がある場合のみ。
デフォルトは dry-run / plan作成のみ。

禁止事項:
  - ALLOW_CLOUDINARY_UPLOAD=false の状態でのアップロード
  - --confirm-upload なしのアップロード
  - --confirm-download なしの外部URLダウンロード
  - 実SNS投稿
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def _detect_media_type(url_or_path: str) -> str:
    """URLまたはファイルパスからメディアタイプを推定する。"""
    s = url_or_path.lower()
    if any(s.endswith(ext) for ext in (".mp4", ".mov", ".avi", ".webm", ".mkv")):
        return "video"
    if any(s.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
        return "image"
    if "video" in s or "/mp4" in s or "amplify_video" in s:
        return "video"
    return "unknown"


def _assess_reuse_risk(
    source_url: str,
    rights_status: str,
    reference_post_id: str = "",
) -> str:
    """メディア再利用リスクを評価する。"""
    if rights_status in ("owned", "licensed"):
        return "low"
    if rights_status == "public_domain":
        return "low"
    if rights_status == "unknown":
        return "high"
    if reference_post_id:
        return "medium"
    if source_url and "example.com" in source_url:
        return "low"
    return "medium"


def build_media_asset(
    account_id: str,
    source_type: str,
    source_url: str = "",
    local_path: str = "",
    reference_post_id: str = "",
    clip_candidate_id: str = "",
    media_type: str = "",
    rights_status: str = "unknown",
    width: int = 0,
    height: int = 0,
    duration_seconds: float = 0.0,
    upload_status: str = "PENDING",
    storage_provider: str = "cloudinary",
    storage_url: str = "",
) -> dict[str, Any]:
    """media_assetsレコードを構築する（実アップロードなし）。"""
    if not media_type:
        media_type = _detect_media_type(source_url or local_path)

    reuse_risk = _assess_reuse_risk(source_url, rights_status, reference_post_id)

    asset_id = f"ma_{_short_uuid()}"

    return {
        "media_asset_id": asset_id,
        "account_id": account_id,
        "source_type": source_type,
        "source_url": source_url,
        "local_path": local_path,
        "reference_post_id": reference_post_id,
        "clip_candidate_id": clip_candidate_id,
        "media_type": media_type,
        "width": width,
        "height": height,
        "duration_seconds": duration_seconds,
        "rights_status": rights_status,
        "reuse_risk": reuse_risk,
        "storage_provider": storage_provider,
        "storage_url": storage_url,
        "upload_status": upload_status,
        "status": "WAITING_REVIEW" if rights_status == "unknown" else "OK",
        "created_at": _now_jst(),
    }


def create_ingestion_plan(
    account_id: str,
    video_url: str = "",
    image_url: str = "",
    local_file: str = "",
    reference_post_id: str = "",
    clip_candidate_id: str = "",
    rights_status: str = "unknown",
    allow_cloudinary_upload: bool = False,
    confirm_upload: bool = False,
    allow_download: bool = False,
    confirm_download: bool = False,
) -> dict[str, Any]:
    """メディア取り込みプランを生成する（実ダウンロード・アップロードなし）。"""
    inputs = []
    if video_url:
        inputs.append(("video_url", video_url))
    if image_url:
        inputs.append(("image_url", image_url))
    if local_file:
        inputs.append(("local_file", local_file))

    if not inputs:
        return {
            "status": "ERROR",
            "error": "入力ソースが指定されていません（--video-url / --image-url / --local-file のいずれかが必要）",
            "assets": [],
        }

    assets = []
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    for source_type, source_value in inputs:
        if source_type in ("video_url", "image_url"):
            if not allow_download or not confirm_download:
                blocked_reasons.append(
                    f"{source_type}={source_value[:50]} の外部ダウンロードには --download --confirm-download が必要です"
                )
                asset = build_media_asset(
                    account_id=account_id,
                    source_type=source_type,
                    source_url=source_value,
                    reference_post_id=reference_post_id,
                    clip_candidate_id=clip_candidate_id,
                    rights_status=rights_status,
                    upload_status="BLOCKED_NO_DOWNLOAD_PERMISSION",
                )
                assets.append(asset)
                continue
            asset = build_media_asset(
                account_id=account_id,
                source_type=source_type,
                source_url=source_value,
                reference_post_id=reference_post_id,
                clip_candidate_id=clip_candidate_id,
                rights_status=rights_status,
                upload_status="DOWNLOADED_NOT_UPLOADED",
            )
            assets.append(asset)
        elif source_type == "local_file":
            if not os.path.isfile(source_value):
                warnings.append(f"local_file が見つかりません: {source_value}")
                upload_status = "LOCAL_FILE_NOT_FOUND"
            else:
                upload_status = "LOCAL_READY"
            asset = build_media_asset(
                account_id=account_id,
                source_type="local_file",
                local_path=source_value,
                reference_post_id=reference_post_id,
                clip_candidate_id=clip_candidate_id,
                rights_status=rights_status,
                upload_status=upload_status,
            )
            assets.append(asset)

    # Cloudinary upload チェック
    for asset in assets:
        if asset["upload_status"] not in ("BLOCKED_NO_DOWNLOAD_PERMISSION", "LOCAL_FILE_NOT_FOUND"):
            if not allow_cloudinary_upload:
                asset["upload_status"] = "BLOCKED_CLOUDINARY_UPLOAD_DISABLED"
                blocked_reasons.append(
                    "Cloudinary upload は ALLOW_CLOUDINARY_UPLOAD=true が必要です"
                )
            elif not confirm_upload:
                asset["upload_status"] = "BLOCKED_NO_UPLOAD_CONFIRMATION"
                blocked_reasons.append(
                    "Cloudinary upload には --upload --confirm-upload が必要です"
                )

        _already_blocked = ("BLOCKED" in asset["upload_status"] or asset["upload_status"] == "LOCAL_FILE_NOT_FOUND")
        if asset.get("reuse_risk") == "high" and not _already_blocked:
            asset["upload_status"] = "BLOCKED_HIGH_REUSE_RISK"
            blocked_reasons.append(
                f"{asset['media_asset_id']}: media_reuse_risk=high のため投稿不可"
            )

    overall_status = "BLOCKED" if blocked_reasons else ("PLAN_OK" if assets else "NO_ASSETS")

    return {
        "account_id": account_id,
        "plan_status": overall_status,
        "assets": assets,
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "asset_count": len(assets),
        "created_at": _now_jst(),
    }
