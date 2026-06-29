#!/usr/bin/env python3
"""test_approve_queue_ready_transition.py — approve_queue.py が WAITING_REVIEW→READY/REJECTED の
人間承認ゲートを担い、投稿は一切しないことを固定する。"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import scripts.approve_queue as aq  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


print("=== test_approve_queue_ready_transition ===\n")

src = (ROOT / "scripts" / "approve_queue.py").read_text(encoding="utf-8")

check("ALLOWED_NEW_STATUSES == {READY, REJECTED}", aq.ALLOWED_NEW_STATUSES == {"READY", "REJECTED"})
check("READY 昇格が許可ステータスに含まれる", "READY" in aq.ALLOWED_NEW_STATUSES)
check("--approve フラグが存在する", "--approve" in src)
check("--reject フラグが存在する", "--reject" in src)
check("--reason を要求する仕組みがある", "--reason" in src)
check("--dry-run フラグが存在する", "--dry-run" in src)

# 投稿系を一切呼ばない（生成・承認専用）
check("ThreadsPublisher を import/呼び出ししない", "ThreadsPublisher" not in src)
check("save_posted_result を呼ばない", "save_posted_result" not in src)
# posted_results への言及は doc/print のみ（書き込みプリミティブと同居しない）
WRITE_PRIMITIVES = ("append_row", "update_row", ".append(", ".update(", "insert_row", "set_values")
posted_lines = [ln for ln in src.splitlines() if "posted_results" in ln]
posted_no_write = all(
    not any(w in ln for w in WRITE_PRIMITIVES) for ln in posted_lines
)
check("posted_results へ書き込みプリミティブを使わない", posted_no_write)
check("PUBLISH_ENABLED=true を設定しない", "PUBLISH_ENABLED=true" not in src and 'PUBLISH_ENABLED\"] = \"true\"' not in src)
check("実投稿フラグ ALLOW_REAL_THREADS_POST を true 化しない", "ALLOW_REAL_THREADS_POST=true" not in src)

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
