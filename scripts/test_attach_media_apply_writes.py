#!/usr/bin/env python3
"""attach_media_to_queue の実書き込みロジックを検証する（Sheets不要）。

- build_attach_write_specs: 付与可否・URL確定/未確定で正しい write spec を作る
- update_queue_fields: queue ヘッダーに存在する列だけ更新し、無い列は skip 報告
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from media.queue_media_attach import build_attach_write_specs  # noqa: E402


def _load_script():
    spec = importlib.util.spec_from_file_location("attach_media_to_queue", ROOT / "scripts/attach_media_to_queue.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _FakeCell:
    def __init__(self, row):
        self.row = row


class _FakeWS:
    def __init__(self, headers, rows):
        self.headers = headers
        self.rows = rows  # list[dict]
        self.updates = []  # (row, col, value)

    def row_values(self, _n):
        return self.headers

    def find(self, value, in_column=None):
        col_name = self.headers[in_column - 1]
        for i, r in enumerate(self.rows):
            if str(r.get(col_name, "")) == value:
                return _FakeCell(i + 2)  # +2: header is row 1
        return None

    def update_cell(self, row, col, value):
        self.updates.append((row, col, value))


def main() -> int:
    mod = _load_script()
    checks: list[tuple[str, bool]] = []

    plans = [
        {"queue_id": "q1", "media_asset_id": "ma1", "attachable": True, "media_url_pending": True, "media_url": ""},
        {"queue_id": "q2", "media_asset_id": "ma2", "attachable": True, "media_url_pending": False, "media_url": "https://x/i.png"},
        {"queue_id": "q3", "media_asset_id": "ma3", "attachable": False, "media_url_pending": False, "media_url": ""},
    ]
    specs = {s["queue_id"]: s for s in build_attach_write_specs(plans)}

    checks.append(("付与不可は spec を作らない", "q3" not in specs))
    checks.append(("pending は PENDING_UPLOAD", specs["q1"]["fields"]["media_status"] == "PENDING_UPLOAD"))
    checks.append(("pending は media_url を書かない", "media_url" not in specs["q1"]["fields"]))
    checks.append(("URL確定は ATTACHED", specs["q2"]["fields"]["media_status"] == "ATTACHED"))
    checks.append(("URL確定は media_url を書く", specs["q2"]["fields"]["media_url"].endswith("i.png")))
    checks.append(("常に media_asset_id を書く", specs["q1"]["fields"]["media_asset_id"] == "ma1"))

    # update_queue_fields: media_asset_id 列のみ存在する queue（media_url/media_status 列なし）
    ws = _FakeWS(["queue_id", "account_id", "media_asset_id"], [{"queue_id": "q2", "media_asset_id": ""}])
    res = mod.update_queue_fields(ws, "q2", specs["q2"]["fields"])
    checks.append(("存在列 media_asset_id は書かれる", "media_asset_id" in res["written"]))
    checks.append(("無い列 media_url は skip", "media_url" in res["skipped"]))
    checks.append(("無い列 media_status は skip", "media_status" in res["skipped"]))
    checks.append(("found=True", res["found"] is True))
    checks.append(("update_cell が1回(asset_idのみ)", len(ws.updates) == 1))

    # 全列が存在する queue → 全部書ける
    ws2 = _FakeWS(["queue_id", "media_asset_id", "media_url", "media_status"], [{"queue_id": "q2"}])
    res2 = mod.update_queue_fields(ws2, "q2", specs["q2"]["fields"])
    checks.append(("全列ありなら skip 無し", res2["skipped"] == []))
    checks.append(("全列ありなら3列書く", set(res2["written"]) == {"media_asset_id", "media_url", "media_status"}))

    # 該当 queue_id が無い → found=False
    res3 = mod.update_queue_fields(ws2, "nope", specs["q2"]["fields"])
    checks.append(("行が無ければ found=False", res3["found"] is False))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
