#!/usr/bin/env python3
"""test_metrics_candidates_draft_not_ready.py — metrics 由来の次回候補が DRAFT であり、
READY でも worker 対象でもないことを固定する。"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import scripts.generate_next_queue_from_metrics as mod  # noqa: E402
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


print("=== test_metrics_candidates_draft_not_ready ===\n")

check("NON_POSTABLE_STATUS == DRAFT", mod.NON_POSTABLE_STATUS == "DRAFT")
check("DRAFT は worker(ELIGIBLE)非対象", mod.NON_POSTABLE_STATUS not in ptq.ELIGIBLE_STATUSES)

ranked = [
    {"result_id": "r1", "content_type": "engagement", "er": 0.12},
    {"result_id": "r2", "content_type": "story", "er": 0.08},
]
drafts, queues, suggestion = mod.build_next_queue_candidates(ranked, "night_scout", 2, "20260628")

check("queue 候補が生成される", len(queues) == 2)
check("全 queue 候補の status は DRAFT", all(q["status"] == "DRAFT" for q in queues))
check("queue 候補に READY が無い", all(q["status"] != "READY" for q in queues))
check("queue 候補は worker 非対象", all(q["status"] not in ptq.ELIGIBLE_STATUSES for q in queues))
check("queue 候補は platform=threads のみ", all(q["platform"] == "threads" for q in queues))
check("queue 候補は auto_publish=false", all(str(q.get("auto_publish", "")).lower() == "false" for q in queues))

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
