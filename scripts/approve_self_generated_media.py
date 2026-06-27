#!/usr/bin/env python3
"""Approve self_generated media for Cloudinary upload (gated Sheets write).

self_generated（自前生成・owned）かつ権利クリアな media_asset の approval_status を
APPROVED にする。第三者 media は対象外（rights が clear でないものは除外）。

安全方針:
  - 既定は計画のみ。実書き込みは --apply かつ --confirm-approve の両方が必要。
  - self_generated（status=SELF_GENERATED）以外は承認しない。
  - 権利が clear でない（no_reuse / plan_only / risk=high 等）ものは承認しない。
  - approval_status を APPROVED にするだけで、learning_rules や source priority は触らない。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from media.queue_media_attach import is_media_rights_clear  # noqa: E402


def select_self_generated_for_approval(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """承認対象（self_generated・権利クリア・未承認）を返す。"""
    out: list[dict[str, Any]] = []
    for a in assets:
        if str(a.get("status", "")).strip().upper() != "SELF_GENERATED":
            continue
        if not is_media_rights_clear(a):
            continue
        if str(a.get("approval_status", "")).strip().upper() == "APPROVED":
            continue  # 既に承認済みは対象外
        out.append(a)
    return out


def update_media_approval(ws, media_asset_id: str) -> dict[str, Any]:
    """media_assets 行の approval_status を APPROVED にする（列があれば）。"""
    headers = ws.row_values(1)
    if "media_asset_id" not in headers:
        raise KeyError("media_assets tab missing media_asset_id header")
    cell = ws.find(media_asset_id, in_column=headers.index("media_asset_id") + 1)
    if cell is None:
        return {"media_asset_id": media_asset_id, "found": False, "written": []}
    written = []
    if "approval_status" in headers:
        ws.update_cell(cell.row, headers.index("approval_status") + 1, "APPROVED")
        written.append("approval_status")
    return {"media_asset_id": media_asset_id, "found": True, "written": written}


def _load_assets(input_json: str | None, apply: bool, account_id: str):
    if input_json:
        with open(input_json, encoding="utf-8") as f:
            assets = json.load(f).get("media_assets", [])
        return None, [a for a in assets if str(a.get("account_id", "")) in ("", account_id)]
    if apply:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        ws = client._ws("media_assets")
        assets = [dict(r) for r in ws.get_all_records() if str(r.get("account_id", "")) in ("", account_id)]
        return ws, assets
    return None, []


def main() -> int:
    parser = argparse.ArgumentParser(description="approve self_generated media (gated)")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--input-json", help='{"media_assets":[...]} for offline planning/testing')
    parser.add_argument("--apply", action="store_true", help="write approval_status=APPROVED (needs --confirm-approve)")
    parser.add_argument("--confirm-approve", action="store_true", help="explicit confirmation for real write")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account は不可"}, ensure_ascii=False))
        return 1

    ws, assets = _load_assets(args.input_json, args.apply, args.account_id)
    targets = select_self_generated_for_approval(assets)
    target_ids = [str(t.get("media_asset_id", "")) for t in targets]

    if not args.apply:
        print(json.dumps({
            "status": "PLAN_ONLY", "account_id": args.account_id,
            "asset_count": len(assets), "approvable_count": len(targets),
            "approvable_ids": target_ids,
            "notes": "書き込み未実行。実承認は --apply --confirm-approve。",
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.confirm_approve:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply には --confirm-approve が必要", "would_approve": target_ids}, ensure_ascii=False))
        return 1
    if ws is None:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply は本番 Sheets 用です（--input-json と併用不可）"}, ensure_ascii=False))
        return 1

    results = [update_media_approval(ws, mid) for mid in target_ids]
    print(json.dumps({
        "status": "APPROVED", "account_id": args.account_id,
        "approved_count": sum(1 for r in results if r["found"]), "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
