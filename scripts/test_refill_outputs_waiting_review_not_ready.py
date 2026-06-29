#!/usr/bin/env python3
"""test_refill_outputs_waiting_review_not_ready.py — refill が WAITING_REVIEW を出力し、
READY を書かないことを固定する（refill は補充であって承認ではない）。"""
from __future__ import annotations
import ast
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


print("=== test_refill_outputs_waiting_review_not_ready ===\n")

path = ROOT / "scripts" / "refill_threads_queue.py"
src = path.read_text(encoding="utf-8")
tree = ast.parse(src)

# build_rows 関数内の status リテラルを収集
build_rows = next(
    (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "build_rows"),
    None,
)
check("build_rows 関数が存在する", build_rows is not None)

status_values: list[str] = []
if build_rows is not None:
    for node in ast.walk(build_rows):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "status" and isinstance(v, ast.Constant):
                    status_values.append(str(v.value))

check("build_rows の status は WAITING_REVIEW を含む", "WAITING_REVIEW" in status_values)
check("build_rows の status に READY を含まない", "READY" not in status_values)
check("補充候補 WAITING_REVIEW は worker 非対象", "WAITING_REVIEW" not in ptq.ELIGIBLE_STATUSES)

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
