"""
cloudinary_client.py — Cloudinary メディア管理（Phase 2.12 で本実装）

Phase 2.8 ではスタブとして public API のみを定義する。
"""
from __future__ import annotations

from typing import Any


def download_media(url: str) -> bytes:
    """URLからメディアをダウンロードする（Phase 2.12 で実装）。"""
    raise NotImplementedError("Phase 2.12 で実装予定")


def upload_to_cloudinary(
    data: bytes,
    public_id: str,
    cloudinary_url: str,
    media_type: str = "image",
) -> dict[str, Any]:
    """メディアをCloudinaryにアップロードしてメタデータを返す（Phase 2.12 で実装）。"""
    raise NotImplementedError("Phase 2.12 で実装予定")


def assess_imitation_risk(media_url: str, text: str) -> str:
    """模倣リスクを判定する（Phase 2.12 で実装）。

    Returns: "low" | "medium" | "high"
    """
    raise NotImplementedError("Phase 2.12 で実装予定")
