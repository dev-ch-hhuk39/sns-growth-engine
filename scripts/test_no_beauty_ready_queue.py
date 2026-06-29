#!/usr/bin/env python3
"""test_no_beauty_ready_queue.py — beauty_account 行は READY でも worker に拾われないことを固定する。
beauty_account は draft_only で対象外。"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import scripts.process_threads_queue as ptq  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


class _FakeWS:
    def __init__(self, rows): self._rows = rows
    def get_all_records(self): return [dict(r) for r in self._rows]


class _FakeClient:
    def __init__(self, rows): self._rows = rows
    def _ws(self, logical): return _FakeWS(self._rows if logical == "queue" else [])


print("=== test_no_beauty_ready_queue ===\n")

check("beauty_account は BEAUTY_BLOCKED に含まれる", "beauty_account" in ptq.BEAUTY_BLOCKED)

rows = [
    {"queue_id": "b-ready", "account_id": "beauty_account", "platform": "threads", "status": "READY", "priority": "1"},
    {"queue_id": "ns-ready", "account_id": "night_scout", "platform": "threads", "status": "READY", "priority": "2"},
]
selected_all = ptq.select_candidates(_FakeClient(rows), None, 10)
sel_ids = {r["queue_id"] for r in selected_all}
check("beauty_account(READY)行は選択されない", "b-ready" not in sel_ids)
check("night_scout(READY)行は選択される", "ns-ready" in sel_ids)

# account_id 指定で beauty を狙っても選択ゼロ
selected_beauty = ptq.select_candidates(_FakeClient(rows), "beauty_account", 10)
check("account_id=beauty_account 指定でも選択ゼロ", selected_beauty == [])

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
