"""Image media asset planning helpers."""
from __future__ import annotations

from typing import Any

from .media_asset_store import build_media_asset, preflight_media_assets


def build_image_assets_from_raw_items(raw_source_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for item in raw_source_items:
        for url in item.get("image_urls", []) or []:
            assets.append(build_media_asset(
                account_id=item.get("target_account_id") or item.get("account_id", ""),
                source_id=item.get("source_id", ""),
                raw_item_id=item.get("raw_item_id", ""),
                media_type="image",
                external_url=url,
                rights_policy=item.get("rights_status", "unknown"),
                reuse_policy=item.get("reuse_policy", "reference_only"),
                media_policy=item.get("media_policy", "plan_only"),
            ))
    return assets


def preflight_image_assets(
    assets: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return preflight_media_assets(assets, sources_by_id, action="post")
