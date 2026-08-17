#!/usr/bin/env python3
"""Beauty READY rows remain scoped and require the dedicated runtime gate."""
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

allowed, reason = ptq.beauty_publish_gate(dry_run=True)
check("Beauty dry-run is enabled by canonical review-gated config", allowed and not reason)
real_allowed, real_reason = ptq.beauty_publish_gate(dry_run=False)
check("Beauty real publish still requires its runtime gate", not real_allowed and bool(real_reason))

rows = [
    {"queue_id": "b-ready", "account_id": "beauty_account", "platform": "threads", "status": "READY", "priority": "1"},
    {"queue_id": "ns-ready", "account_id": "night_scout", "platform": "threads", "status": "READY", "priority": "2"},
]
selected_all = ptq.select_candidates(_FakeClient(rows), None, 10)
sel_ids = {r["queue_id"] for r in selected_all}
check("generic selector may inspect Beauty READY row", "b-ready" in sel_ids)
check("night_scout(READY)行は選択される", "ns-ready" in sel_ids)

# Account-specific selection is followed by beauty_publish_gate in main/process_one.
selected_beauty = ptq.select_candidates(_FakeClient(rows), "beauty_account", 10)
check("account_id=beauty_account selection remains scoped", [r["queue_id"] for r in selected_beauty] == ["b-ready"])

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
