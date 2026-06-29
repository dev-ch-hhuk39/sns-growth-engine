#!/usr/bin/env python3
"""test_no_x_ready_queue.py — X(platform=x)行は READY でも worker に拾われないことを固定する。
X は将来対応であり、現状 Threads worker は threads 以外を投稿対象にしない。"""
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


print("=== test_no_x_ready_queue ===\n")

rows = [
    {"queue_id": "x-ready", "account_id": "night_scout", "platform": "x", "status": "READY", "priority": "1"},
    {"queue_id": "x-wait", "account_id": "night_scout", "platform": "x", "status": "WAITING_REVIEW", "priority": "2"},
    {"queue_id": "th-ready", "account_id": "night_scout", "platform": "threads", "status": "READY", "priority": "3"},
]
selected = ptq.select_candidates(_FakeClient(rows), None, 10)
sel_ids = {r["queue_id"] for r in selected}

check("X(READY)行は選択されない", "x-ready" not in sel_ids)
check("X(WAITING_REVIEW)行は選択されない", "x-wait" not in sel_ids)
check("threads(READY)行のみ選択される", sel_ids == {"th-ready"})
check("選択行は全て platform=threads", all(str(r.get("platform", "")).lower() == "threads" for r in selected))

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
