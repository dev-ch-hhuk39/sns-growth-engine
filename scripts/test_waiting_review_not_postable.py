#!/usr/bin/env python3
"""test_waiting_review_not_postable.py — WAITING_REVIEW が投稿対象に絶対ならないことを固定する。"""
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


print("=== test_waiting_review_not_postable ===\n")

check("WAITING_REVIEW は ELIGIBLE_STATUSES に含まれない", "WAITING_REVIEW" not in ptq.ELIGIBLE_STATUSES)

# WAITING_REVIEW のみの queue → 選択ゼロ
rows = [
    {"queue_id": f"q{i}", "account_id": "night_scout", "platform": "threads", "status": "WAITING_REVIEW", "priority": str(i)}
    for i in range(5)
]
selected = ptq.select_candidates(_FakeClient(rows), "night_scout", 10)
check("WAITING_REVIEW のみの queue では選択ゼロ", selected == [])

# WAITING_REVIEW と READY 混在 → READY だけ
mixed = rows + [{"queue_id": "q-ready", "account_id": "night_scout", "platform": "threads", "status": "READY", "priority": "0"}]
selected2 = ptq.select_candidates(_FakeClient(mixed), "night_scout", 10)
check("混在時も WAITING_REVIEW は選ばれず READY のみ", [r["queue_id"] for r in selected2] == ["q-ready"])

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
