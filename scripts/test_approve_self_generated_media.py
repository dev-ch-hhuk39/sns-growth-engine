#!/usr/bin/env python3
"""approve_self_generated_media の選定・書き込みロジックを検証する（Sheets不要）。

- select_self_generated_for_approval: self_generated かつ権利クリアかつ未承認だけ選ぶ
- update_media_approval: approval_status 列があれば APPROVED を書く / 無ければ skip
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/approve_self_generated_media.py"


def _load():
    spec = importlib.util.spec_from_file_location("approve_self_generated_media", SCRIPT)
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
        self.rows = rows
        self.updates = []  # (row, col, value)

    def row_values(self, _n):
        return self.headers

    def find(self, value, in_column=None):
        col_name = self.headers[in_column - 1]
        for i, r in enumerate(self.rows):
            if str(r.get(col_name, "")) == value:
                return _FakeCell(i + 2)
        return None

    def update_cell(self, row, col, value):
        self.updates.append((row, col, value))


def main() -> int:
    mod = _load()
    select = mod.select_self_generated_for_approval
    checks: list[tuple[str, bool]] = []

    assets = [
        # 承認対象: self_generated・owned・未承認
        {"media_asset_id": "ma_self", "status": "SELF_GENERATED",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned"},
        # 既に承認済み → 対象外
        {"media_asset_id": "ma_done", "status": "SELF_GENERATED", "approval_status": "APPROVED",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned"},
        # self_generated でない → 対象外
        {"media_asset_id": "ma_third", "status": "WAITING_REVIEW",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned"},
        # self_generated だが権利クリアでない（no_reuse） → 対象外
        {"media_asset_id": "ma_nr", "status": "SELF_GENERATED",
         "rights_policy": "owned", "reuse_policy": "no_reuse", "media_policy": "owned"},
        # self_generated だが risk=high → 対象外
        {"media_asset_id": "ma_hr", "status": "SELF_GENERATED", "media_reuse_risk": "high",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned"},
    ]
    targets = select(assets)
    target_ids = {t["media_asset_id"] for t in targets}

    checks.append(("self_generated・clear・未承認のみ選ぶ", target_ids == {"ma_self"}))
    checks.append(("承認済みは除外", "ma_done" not in target_ids))
    checks.append(("第三者(非self_generated)は除外", "ma_third" not in target_ids))
    checks.append(("no_reuse は除外", "ma_nr" not in target_ids))
    checks.append(("risk=high は除外", "ma_hr" not in target_ids))

    # update_media_approval: approval_status 列あり
    ws = _FakeWS(["media_asset_id", "status", "approval_status"],
                 [{"media_asset_id": "ma_self", "status": "SELF_GENERATED", "approval_status": ""}])
    res = mod.update_media_approval(ws, "ma_self")
    checks.append(("found=True", res["found"] is True))
    checks.append(("approval_status を書く", "approval_status" in res["written"]))
    checks.append(("APPROVED を書き込む", ws.updates and ws.updates[0][2] == "APPROVED"))

    # approval_status 列が無い → 書かない（skip 相当: written 空）
    ws2 = _FakeWS(["media_asset_id", "status"],
                  [{"media_asset_id": "ma_self", "status": "SELF_GENERATED"}])
    res2 = mod.update_media_approval(ws2, "ma_self")
    checks.append(("approval_status 列なしは written 空", res2["written"] == []))
    checks.append(("列なしでも found=True", res2["found"] is True))

    # 該当 id が無い → found=False
    res3 = mod.update_media_approval(ws, "nope")
    checks.append(("行が無ければ found=False", res3["found"] is False))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
