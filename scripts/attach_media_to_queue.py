#!/usr/bin/env python3
"""Plan media attachment to Threads queue rows (dry-run only).

安全方針:
  - 計画のみ。Sheets への書き込みは行わない（本番書き込みは別途ユーザー判断）。
  - 権利クリア（APPROVED/READY/SELF_GENERATED かつ owned/allowed/approved 等）な
    media_asset だけを付与候補にする。
  - URL 未確定（Cloudinary upload 前）の self_generated カードは「pending」として表示する。

入力:
  --input-json に {"queue_rows": [...], "media_assets": [...]} を渡す（オフライン計画）。

使い方:
  python3 scripts/attach_media_to_queue.py --account-id night_scout --input-json plan.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.queue_media_attach import plan_queue_media_attachment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="plan media attachment to queue (dry-run only)")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--input-json", required=True, help='{"queue_rows":[...],"media_assets":[...]}')
    args = parser.parse_args()

    with open(args.input_json, encoding="utf-8") as f:
        data = json.load(f)

    queue_rows = [r for r in data.get("queue_rows", []) if str(r.get("account_id", "")) in ("", args.account_id)]
    assets = data.get("media_assets", [])
    assets_by_id = {str(a.get("media_asset_id", "")): a for a in assets}

    plans = plan_queue_media_attachment(queue_rows, assets_by_id)
    attachable = [p for p in plans if p["attachable"]]
    pending = [p for p in attachable if p["media_url_pending"]]

    print(json.dumps({
        "status": "PLAN_ONLY",
        "account_id": args.account_id,
        "queue_count": len(queue_rows),
        "attachable_count": len(attachable),
        "pending_url_count": len(pending),
        "plans": plans,
        "notes": "Sheetsへの書き込みは未実行。本番付与は別途ユーザー判断。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
