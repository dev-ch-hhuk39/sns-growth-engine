"""Plan media attachment to queue rows — rights-clear media のみ対象。

このモジュールは「どの media_asset をどの queue 行に付けてよいか」を**計画するだけ**。
Sheets への書き込みは行わない（本番書き込みは別途ユーザー判断）。

付与してよい media の条件（いずれも満たすこと）:
  - status        : APPROVED / READY / SELF_GENERATED のいずれか
  - rights_policy  : owned / allowed / approved のいずれか（unknown / not_allowed は不可）
  - reuse_policy   : no_reuse ではない
  - media_policy   : do_not_download / plan_only ではない
  - media_reuse_risk: high ではない（欄があれば）
"""
from __future__ import annotations

from typing import Any

OK_STATUS = {"APPROVED", "READY", "SELF_GENERATED"}
OK_RIGHTS = {"owned", "allowed", "approved"}
BLOCK_MEDIA_POLICY = {"do_not_download", "plan_only"}


def media_rights_blockers(asset: dict[str, Any]) -> list[str]:
    """付与不可の理由を列挙する。空なら付与可。"""
    reasons: list[str] = []
    status = str(asset.get("status", "")).upper()
    if status not in OK_STATUS:
        reasons.append(f"status={status or '(empty)'}: APPROVED/READY/SELF_GENERATED以外は不可")
    rights = str(asset.get("rights_policy", "")).lower()
    if rights not in OK_RIGHTS:
        reasons.append(f"rights_policy={rights or '(empty)'}: owned/allowed/approved以外は不可")
    if str(asset.get("reuse_policy", "")).lower() == "no_reuse":
        reasons.append("reuse_policy=no_reuse: 再利用不可")
    if str(asset.get("media_policy", "")).lower() in BLOCK_MEDIA_POLICY:
        reasons.append(f"media_policy={asset.get('media_policy')}: 付与不可")
    if str(asset.get("media_reuse_risk", "")).lower() == "high":
        reasons.append("media_reuse_risk=high: 付与不可")
    return reasons


def is_media_rights_clear(asset: dict[str, Any]) -> bool:
    return not media_rights_blockers(asset)


def resolve_media_url(asset: dict[str, Any]) -> str:
    """投稿に使う URL を解決する。未 upload なら空（pending）。"""
    for key in ("cloudinary_url", "storage_url", "external_url"):
        url = str(asset.get(key, "") or "").strip()
        if url:
            return url
    return ""


def select_attachable_media(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """権利クリアな media_asset のみ返す。"""
    return [a for a in assets if is_media_rights_clear(a)]


def plan_queue_media_attachment(
    queue_rows: list[dict[str, Any]],
    assets_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """各 queue 行に対する media 付与計画を返す（書き込みはしない）。

    queue 行の `media_asset_id` が指す asset を検査し、付与可否と URL を決める。
    """
    plans: list[dict[str, Any]] = []
    for row in queue_rows:
        queue_id = str(row.get("queue_id", ""))
        media_asset_id = str(row.get("media_asset_id", "") or "")
        plan: dict[str, Any] = {
            "queue_id": queue_id,
            "media_asset_id": media_asset_id,
            "attachable": False,
            "media_url": "",
            "media_url_pending": False,
            "reasons": [],
        }
        if not media_asset_id:
            plan["reasons"] = ["queue 行に media_asset_id がない（text-only）"]
            plans.append(plan)
            continue
        asset = assets_by_id.get(media_asset_id)
        if asset is None:
            plan["reasons"] = [f"media_asset_id={media_asset_id} が media_assets に見つからない"]
            plans.append(plan)
            continue
        blockers = media_rights_blockers(asset)
        if blockers:
            plan["reasons"] = blockers
            plans.append(plan)
            continue
        url = resolve_media_url(asset)
        plan["attachable"] = True
        plan["media_url"] = url
        plan["media_url_pending"] = url == ""
        plan["reasons"] = (
            ["権利クリア。ただし URL 未確定（Cloudinary upload 前）"]
            if url == ""
            else ["権利クリア・URL 確定"]
        )
        plans.append(plan)
    return plans
