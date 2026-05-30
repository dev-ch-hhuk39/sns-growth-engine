"""
cloudinary_client.py — Cloudinary メディア管理（Phase 2.12）

reference_posts から抽出した画像・動画URLを管理し、
Cloudinaryへのアップロード基盤を提供する。

安全ガード（2重）:
  dry_run=True               → アップロードしない（デフォルト）
  ALLOW_CLOUDINARY_UPLOAD != true → アップロードしない（デフォルト false）

両方が解除された場合のみ実際の HTTP POST を実行する。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import requests

JST = timezone(timedelta(hours=9))

VIDEO_PATTERNS = (".mp4", ".mov", "amplify_video", "/video/")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

CLOUDINARY_UPLOAD_URL = "https://api.cloudinary.com/v1_1/{cloud_name}/{resource_type}/upload"


# ------------------------------------------------------------------ #
# URL ユーティリティ
# ------------------------------------------------------------------ #

def extract_media_urls(post: dict) -> list[str]:
    """投稿から有効なメディアURLリストを返す。

    media_urls（パイプ区切り文字列）と image_urls / video_urls（リストまたはパイプ区切り）
    の両方を処理する。重複は除去し、空文字は除外する。
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(value: Any) -> None:
        if isinstance(value, list):
            for v in value:
                url = str(v or "").strip()
                if url and url not in seen:
                    seen.add(url)
                    result.append(url)
        elif isinstance(value, str):
            for part in value.split("|"):
                url = part.strip()
                if url and url not in seen:
                    seen.add(url)
                    result.append(url)

    _add(post.get("media_urls", ""))
    _add(post.get("image_urls", ""))
    _add(post.get("video_urls", ""))
    return result


def classify_media_url(url: str) -> str:
    """URLから `image` / `video` / `unknown` を判定する。"""
    lower = url.lower()
    for pattern in VIDEO_PATTERNS:
        if pattern in lower:
            return "video"
    for ext in IMAGE_EXTENSIONS:
        if lower.endswith(ext):
            return "image"
    if "/image/" in lower or "pbs.twimg.com" in lower:
        return "image"
    if lower:
        return "unknown"
    return "unknown"


# ------------------------------------------------------------------ #
# ID / Slug 生成
# ------------------------------------------------------------------ #

def safe_slug(text: str, fallback: str = "unknown") -> str:
    """テキストをファイル名安全なスラグに変換する。"""
    if not text:
        return fallback
    normalized = unicodedata.normalize("NFKC", text)
    slug = re.sub(r"[^\w\-]", "_", normalized).strip("_")
    return slug or fallback


def build_public_id(reference_post_id: str, account_id: str, index: int = 0) -> str:
    """Cloudinary public_id を生成する。

    形式: sns-growth-engine/{account_slug}/{post_id}-{index:02d}
    """
    account_slug = safe_slug(account_id, "account")
    post_slug = safe_slug(reference_post_id, "post")
    return f"sns-growth-engine/{account_slug}/{post_slug}-{index:02d}"


# ------------------------------------------------------------------ #
# Cloudinary API
# ------------------------------------------------------------------ #

def cloudinary_signature(params: dict[str, str], api_secret: str) -> str:
    """Cloudinary API リクエスト署名を生成する（SHA-1）。"""
    filtered = {k: v for k, v in params.items() if v not in (None, "", [])}
    payload = "&".join(f"{key}={filtered[key]}" for key in sorted(filtered))
    return hashlib.sha1(f"{payload}{api_secret}".encode("utf-8")).hexdigest()


def download_media(url: str) -> tuple[bytes, str]:
    """URLからメディアをダウンロードして (bytes, mime_type) を返す。

    ダウンロードに失敗した場合は requests.HTTPError を送出する。
    """
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    mime = response.headers.get("Content-Type", "").split(";")[0].strip()
    if not mime:
        lower = url.lower()
        if lower.endswith(".mp4") or "video" in lower:
            mime = "video/mp4"
        elif lower.endswith(".mov"):
            mime = "video/quicktime"
        elif lower.endswith(".png"):
            mime = "image/png"
        elif lower.endswith(".gif"):
            mime = "image/gif"
        elif lower.endswith(".webp"):
            mime = "image/webp"
        else:
            mime = "image/jpeg"
    return response.content, mime


def upload_to_cloudinary(
    data: bytes,
    mime_type: str,
    public_id: str,
    config: dict[str, Any],
) -> str:
    """Cloudinaryへメディアをアップロードして secure_url を返す。

    config は get_cloudinary_config() の戻り値を想定する。
    allow_upload が False の場合は RuntimeError を送出する（呼び出し前にガードすること）。
    """
    if not config.get("allow_upload"):
        raise RuntimeError(
            "ALLOW_CLOUDINARY_UPLOAD が false のためアップロードできません。"
            " .env で ALLOW_CLOUDINARY_UPLOAD=true に設定してください。"
        )

    cloud_name = config.get("cloud_name", "")
    api_key = config.get("api_key", "")
    api_secret = config.get("api_secret", "")

    if not cloud_name or not api_key or not api_secret:
        raise ValueError(
            "Cloudinary 認証情報が不足しています。"
            " CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET を設定してください。"
        )

    resource_type = "video" if mime_type.startswith("video/") else "image"
    timestamp = str(int(datetime.now(JST).timestamp()))

    params = {
        "public_id": public_id,
        "timestamp": timestamp,
    }
    signature = cloudinary_signature(params, api_secret)

    url = CLOUDINARY_UPLOAD_URL.format(cloud_name=cloud_name, resource_type=resource_type)
    resp = requests.post(
        url,
        data={
            "api_key": api_key,
            "timestamp": timestamp,
            "public_id": public_id,
            "signature": signature,
        },
        files={"file": ("media", data, mime_type)},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["secure_url"]


# ------------------------------------------------------------------ #
# リスク判定
# ------------------------------------------------------------------ #

def assess_imitation_risk(post: dict) -> str:
    """メディアの模倣リスクを返す: `low` / `medium` / `high` / `unknown`。

    動画URLが含まれる場合は high、画像URLのみなら medium、URLなしなら unknown。
    """
    urls = extract_media_urls(post)
    if not urls:
        return "unknown"
    for url in urls:
        if classify_media_url(url) == "video":
            return "high"
    return "medium"


# ------------------------------------------------------------------ #
# メディアアセット準備
# ------------------------------------------------------------------ #

def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def prepare_media_asset(
    post: dict,
    account_id: str,
    config: dict[str, Any] | None = None,
    dry_run: bool = True,
    index: int = 0,
    original_media_url: str = "",
) -> dict[str, Any]:
    """1件のメディアURLからメディアアセット dict を生成する。

    dry_run=True または config.allow_upload=False の場合、
    Cloudinaryへのアップロードはスキップし storage_provider="dry_run" とする。
    """
    if config is None:
        config = {}

    allow_upload = (not dry_run) and config.get("allow_upload", False)

    media_type = classify_media_url(original_media_url)
    imitation_risk = assess_imitation_risk(post)

    reference_post_id = str(
        post.get("id") or post.get("post_id") or post.get("reference_post_id") or ""
    ).strip()
    public_id = build_public_id(reference_post_id, account_id, index)

    asset: dict[str, Any] = {
        "media_id": str(uuid4()),
        "account_id": account_id,
        "reference_post_id": reference_post_id,
        "source_platform": str(post.get("platform", "x")).strip(),
        "source_post_url": str(post.get("url", post.get("post_url", ""))).strip(),
        "original_media_url": original_media_url,
        "storage_provider": "dry_run" if dry_run else "none",
        "storage_url": "",
        "cloudinary_public_id": public_id if allow_upload else "",
        "media_type": media_type,
        "mime_type": "",
        "width": "",
        "height": "",
        "duration": "",
        "reuse_status": "reference_only",
        "media_reuse_risk": imitation_risk,
        "imitation_risk": imitation_risk,
        "downloaded_at": "",
        "uploaded_at": "",
        "used_count": "0",
        "notes": "",
    }

    if allow_upload:
        try:
            data, mime_type = download_media(original_media_url)
            asset["mime_type"] = mime_type
            asset["downloaded_at"] = _now_jst()
            storage_url = upload_to_cloudinary(data, mime_type, public_id, config)
            asset["storage_url"] = storage_url
            asset["storage_provider"] = "cloudinary"
            asset["uploaded_at"] = _now_jst()
            print(f"[cloudinary] uploaded: {public_id} → {storage_url[:60]}...")
        except Exception as e:
            print(f"[ERROR] Cloudinary upload failed for {original_media_url!r}: {e}")
            asset["notes"] = f"upload_error: {e}"
    else:
        if dry_run:
            print(f"[dry-run] prepare_media_asset: {original_media_url!r} (skip upload)")
        else:
            print(f"[prepare] media_asset recorded (no upload): {original_media_url!r}")

    return asset


def prepare_media_assets(
    posts: list[dict],
    account_id: str,
    config: dict[str, Any] | None = None,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """複数投稿からメディアアセットを一括生成する。

    メディアURLが存在しない投稿はスキップする。
    1件の投稿に複数URLがある場合はそれぞれ別のアセットとして生成する。
    """
    if config is None:
        config = {}
    assets: list[dict[str, Any]] = []
    for post in posts:
        urls = extract_media_urls(post)
        if not urls:
            continue
        for idx, url in enumerate(urls):
            asset = prepare_media_asset(
                post=post,
                account_id=account_id,
                config=config,
                dry_run=dry_run,
                index=idx,
                original_media_url=url,
            )
            assets.append(asset)
    return assets
