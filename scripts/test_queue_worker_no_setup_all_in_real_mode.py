#!/usr/bin/env python3
"""test_queue_worker_no_setup_all_in_real_mode.py — real_post モードで setup_all が呼ばれないことを確認。"""
from __future__ import annotations
import sys, ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

PASS_COUNT = FAIL_COUNT = 0


def check(label: str, cond: bool) -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS {label}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL {label}")


print("=== test_queue_worker_no_setup_all_in_real_mode ===\n")

script_path = ROOT / "scripts" / "process_threads_queue.py"
source = script_path.read_text(encoding="utf-8")

# 1. setup_all() の実呼び出しが main() に存在しないこと
# (コメント行・文字列内を除く)
lines = source.splitlines()
setup_all_lines = [
    (i + 1, line)
    for i, line in enumerate(lines)
    if "setup_all()" in line and not line.strip().startswith("#")
]
check("main() に setup_all() の実呼び出しが存在しない", len(setup_all_lines) == 0)

# 2. _get_headers 関数が定義されていること
check("_get_headers 関数が定義されている", "def _get_headers(" in source)

# 3. _headers_cache が定義されていること
check("_headers_cache が定義されている", "_headers_cache" in source)

# 4. time.sleep が _get_headers 内で使われている（バックオフ実装の証拠）
check("time.sleep がソース内で使われている", "time.sleep" in source)

# 5. append_row が _get_headers を使っている（ws.row_values(1) を直接呼ばない）
in_append_row = False
append_row_lines: list[str] = []
for line in lines:
    if line.startswith("def append_row("):
        in_append_row = True
    elif in_append_row and line.startswith("def ") and "append_row" not in line:
        break
    if in_append_row:
        append_row_lines.append(line)

append_uses_cache = any("_get_headers" in l for l in append_row_lines)
append_direct_row_values = any(
    "ws.row_values(1)" in l and not l.strip().startswith("#")
    for l in append_row_lines
)
check("append_row が _get_headers を使っている", append_uses_cache)
check("append_row が ws.row_values(1) を直接呼ばない", not append_direct_row_values)

# 6. update_row が _get_headers を使っている
in_update_row = False
update_row_lines: list[str] = []
for line in lines:
    if line.startswith("def update_row("):
        in_update_row = True
    elif in_update_row and line.startswith("def ") and "update_row" not in line:
        break
    if in_update_row:
        update_row_lines.append(line)

update_uses_cache = any("_get_headers" in l for l in update_row_lines)
update_direct_row_values = any(
    "ws.row_values(1)" in l and not l.strip().startswith("#")
    for l in update_row_lines
)
check("update_row が _get_headers を使っている", update_uses_cache)
check("update_row が ws.row_values(1) を直接呼ばない", not update_direct_row_values)

# 7. ELIGIBLE_STATUSES に PROCESSING が含まれないこと（PROCESSING 行を再処理しない）
import scripts.process_threads_queue as ptq
check("ELIGIBLE_STATUSES に PROCESSING が含まれない", "PROCESSING" not in ptq.ELIGIBLE_STATUSES)

# 8. FINAL_OR_LOCKED_STATUSES に PROCESSING が含まれること
check("FINAL_OR_LOCKED_STATUSES に PROCESSING が含まれる", "PROCESSING" in ptq.FINAL_OR_LOCKED_STATUSES)

# 9. beauty_account は BEAUTY_BLOCKED に含まれること
check("beauty_account は BEAUTY_BLOCKED に含まれる", "beauty_account" in ptq.BEAUTY_BLOCKED)

# 10. workflow ファイルに setup_all が含まれないこと（念のため確認）
workflow_path = ROOT / ".github" / "workflows" / "threads-queue-worker.yml"
workflow_src = workflow_path.read_text(encoding="utf-8")
check("threads-queue-worker.yml に setup_all が含まれない", "setup_all" not in workflow_src)

print(f"\n--- 結果 ---")
print(f"PASS: {PASS_COUNT} / FAIL: {FAIL_COUNT}")
sys.exit(0 if FAIL_COUNT == 0 else 1)
