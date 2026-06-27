#!/usr/bin/env python3
"""Plan and (optionally) apply media attachment to Threads queue rows.

安全方針:
  - 既定は計画のみ（PLAN_ONLY）。Sheets 書き込みは行わない。
  - 実書き込みは --apply かつ --confirm-attach の両方が必要。
  - 権利クリア（APPROVED/READY/SELF_GENERATED かつ owned/allowed/approved 等）な
    media_asset だけを付与候補にする。
  - URL 未確定（Cloudinary upload 前）の self_generated カードは media_url を書かず
    media_status=PENDING_UPLOAD として記録する（誤って空 URL で ATTACHED にしない）。
  - queue タブに無い列（media_url / media_status 等）は書き込みをスキップし、
    skipped_fields として報告する（安全書込。存在する列だけ更新する）。

入力:
  --input-json に {"queue_rows":[...],"media_assets":[...]} を渡すとオフライン計画。
  --apply 時に --input-json が無ければ本番 Sheets の queue / media_assets を読む。

使い方:
  # 計画のみ（オフライン）
  python3 scripts/attach_media_to_queue.py --account-id night_scout --input-json plan.json
  # 本番 queue へ付与（要明示確認）
  python3 scripts/attach_media_to_queue.py --account-id night_scout --apply --confirm-attach
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from media.queue_media_attach import (  # noqa: E402
    build_attach_write_specs,
    plan_queue_media_attachment,
)


def update_queue_fields(ws, queue_id: str, fields: dict) -> dict:
    """queue 行の存在する列だけを更新する。書いた列・無い列を返す。"""
    headers = ws.row_values(1)
    if "queue_id" not in headers:
        raise KeyError("queue tab missing queue_id header")
    cell = ws.find(queue_id, in_column=headers.index("queue_id") + 1)
    written, skipped = [], []
    if cell is None:
        return {"queue_id": queue_id, "found": False, "written": [], "skipped": list(fields)}
    for field, value in fields.items():
        if field in headers:
            ws.update_cell(cell.row, headers.index(field) + 1, str(value))
            written.append(field)
        else:
            skipped.append(field)
    return {"queue_id": queue_id, "found": True, "written": written, "skipped": skipped}


def _load_offline(input_json: str, account_id: str):
    with open(input_json, encoding="utf-8") as f:
        data = json.load(f)
    queue_rows = [r for r in data.get("queue_rows", []) if str(r.get("account_id", "")) in ("", account_id)]
    assets_by_id = {str(a.get("media_asset_id", "")): a for a in data.get("media_assets", [])}
    return queue_rows, assets_by_id


def _load_live(account_id: str):
    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    queue_ws = client._ws("queue")
    media_ws = client._ws("media_assets")
    queue_rows = [
        dict(r) for r in queue_ws.get_all_records()
        if str(r.get("account_id", "")) == account_id and str(r.get("platform", "")).lower() == "threads"
    ]
    assets_by_id = {str(a.get("media_asset_id", "")): dict(a) for a in media_ws.get_all_records()}
    return client, queue_ws, queue_rows, assets_by_id


def main() -> int:
    parser = argparse.ArgumentParser(description="plan/apply media attachment to queue")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--input-json", help='{"queue_rows":[...],"media_assets":[...]} for offline planning')
    parser.add_argument("--apply", action="store_true", help="write media fields to queue (needs --confirm-attach)")
    parser.add_argument("--confirm-attach", action="store_true", help="explicit confirmation for real write")
    args = parser.parse_args()

    queue_ws = None
    if args.input_json:
        queue_rows, assets_by_id = _load_offline(args.input_json, args.account_id)
    elif args.apply:
        _client, queue_ws, queue_rows, assets_by_id = _load_live(args.account_id)
    else:
        print(json.dumps({"status": "ERROR", "reason": "--input-json or --apply required"}, ensure_ascii=False))
        return 1

    plans = plan_queue_media_attachment(queue_rows, assets_by_id)
    attachable = [p for p in plans if p["attachable"]]
    pending = [p for p in attachable if p["media_url_pending"]]
    specs = build_attach_write_specs(plans)

    if not args.apply:
        print(json.dumps({
            "status": "PLAN_ONLY",
            "account_id": args.account_id,
            "queue_count": len(queue_rows),
            "attachable_count": len(attachable),
            "pending_url_count": len(pending),
            "plans": plans,
            "write_specs": specs,
            "notes": "Sheetsへの書き込みは未実行。実書き込みは --apply --confirm-attach。",
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.confirm_attach:
        print(json.dumps({
            "status": "BLOCKED",
            "reason": "--apply には --confirm-attach が必要です",
            "would_write": specs,
        }, ensure_ascii=False, indent=2))
        return 1

    if queue_ws is None:  # --apply + --input-json はオフラインなので書けない
        print(json.dumps({"status": "BLOCKED", "reason": "--apply は本番 Sheets 用です（--input-json と併用不可）"}, ensure_ascii=False))
        return 1

    results = [update_queue_fields(queue_ws, s["queue_id"], s["fields"]) for s in specs]
    print(json.dumps({
        "status": "APPLIED",
        "account_id": args.account_id,
        "applied_count": sum(1 for r in results if r["found"]),
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
