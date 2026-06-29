#!/usr/bin/env python3
"""test_generated_ideas_waiting_review_not_ready.py — Threads 投稿案生成は WAITING_REVIEW を出し、
READY を直接書かず、worker 非対象であることを固定する。"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import scripts.generate_threads_ideas_from_references as gen  # noqa: E402
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


print("=== test_generated_ideas_waiting_review_not_ready ===\n")

check("生成候補 status は WAITING_REVIEW", gen.CANDIDATE_STATUS == "WAITING_REVIEW")
check("生成候補 status は READY ではない", gen.CANDIDATE_STATUS != "READY")
check("WAITING_REVIEW は worker(ELIGIBLE)非対象", gen.CANDIDATE_STATUS not in ptq.ELIGIBLE_STATUSES)
check("ローカル ELIGIBLE_STATUSES が worker と一致(={READY})", gen.ELIGIBLE_STATUSES == ptq.ELIGIBLE_STATUSES == {"READY"})

src = (ROOT / "scripts" / "generate_threads_ideas_from_references.py").read_text(encoding="utf-8")
check("生成系が status=READY を直接書かない", '"status": "READY"' not in src and "'status': 'READY'" not in src)

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
