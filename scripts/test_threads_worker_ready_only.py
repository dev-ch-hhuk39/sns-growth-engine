#!/usr/bin/env python3
"""test_threads_worker_ready_only.py — Threads worker の投稿対象が READY のみであることを行動レベルで固定する。

select_candidates() に READY / WAITING_REVIEW / PLANNED / DRAFT / POSTED を混在させ、
READY 行だけが選択されることを確認する（回帰固定）。
"""
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
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def get_all_records(self) -> list[dict]:
        return [dict(r) for r in self._rows]


class _FakeClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def _ws(self, logical: str):
        return _FakeWS(self._rows if logical == "queue" else [])


print("=== test_threads_worker_ready_only ===\n")

# 定数レベル
check("ELIGIBLE_STATUSES == {READY}", ptq.ELIGIBLE_STATUSES == {"READY"})

rows = [
    {"queue_id": "q-ready", "account_id": "night_scout", "platform": "threads", "status": "READY", "priority": "1"},
    {"queue_id": "q-wait", "account_id": "night_scout", "platform": "threads", "status": "WAITING_REVIEW", "priority": "2"},
    {"queue_id": "q-plan", "account_id": "night_scout", "platform": "threads", "status": "PLANNED", "priority": "3"},
    {"queue_id": "q-draft", "account_id": "night_scout", "platform": "threads", "status": "DRAFT", "priority": "4"},
    {"queue_id": "q-posted", "account_id": "night_scout", "platform": "threads", "status": "POSTED", "priority": "5"},
    {"queue_id": "q-ready2", "account_id": "night_scout", "platform": "threads", "status": "READY", "priority": "0"},
]
selected = ptq.select_candidates(_FakeClient(rows), "night_scout", 10)
sel_ids = {r["queue_id"] for r in selected}
sel_statuses = {str(r.get("status", "")).upper() for r in selected}

check("READY 行のみ選択される", sel_ids == {"q-ready", "q-ready2"})
check("選択行の status は全て READY", sel_statuses == {"READY"})
check("WAITING_REVIEW は選択されない", "q-wait" not in sel_ids)
check("PLANNED は選択されない", "q-plan" not in sel_ids)
check("DRAFT は選択されない", "q-draft" not in sel_ids)
check("POSTED は選択されない", "q-posted" not in sel_ids)
check("priority 昇順で並ぶ（q-ready2 が先）", [r["queue_id"] for r in selected] == ["q-ready2", "q-ready"])

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
