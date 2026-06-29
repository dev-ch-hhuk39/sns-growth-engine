#!/usr/bin/env python3
"""test_workflows_do_not_publish_waiting_review.py — GitHub Actions が WAITING_REVIEW を投稿しない／
定時実行は dry-run のみ／queue worker の実投稿フラグ既定が false であることを固定する。"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


print("=== test_workflows_do_not_publish_waiting_review ===\n")

wf_dir = ROOT / ".github" / "workflows"
workflows = {p.name: p.read_text(encoding="utf-8") for p in sorted(wf_dir.glob("*.yml"))}
check("workflow ファイルが存在する", len(workflows) > 0)

# 1. queue worker を起動する workflow は eligibility を上書きしない
#    （WAITING_REVIEW / PLANNED を投稿対象として渡す手段が無いこと）
PUBLISH_CONFIRM_TOKENS = ("--confirm-real-post", "--no-dry-run")
for name, src in workflows.items():
    if "process_threads_queue.py" not in src:
        continue
    no_status_override = "ELIGIBLE_STATUSES" not in src
    no_wr_publish = "--status WAITING_REVIEW" not in src and "--status PLANNED" not in src
    check(f"{name}: worker の eligibility を上書きしない", no_status_override and no_wr_publish)

# 2. 定時実行(schedule)を持つ workflow は publish 確定フラグを含まない（dry-run のみ）
for name, src in workflows.items():
    if "schedule:" not in src:
        continue
    has_publish_confirm = any(tok in src for tok in PUBLISH_CONFIRM_TOKENS)
    static_publish_true = 'PUBLISH_ENABLED: "true"' in src or 'ALLOW_REAL_THREADS_POST: "true"' in src
    check(f"{name}: 定時実行は実投稿確定フラグを持たない", not has_publish_confirm)
    check(f"{name}: 定時実行は実投稿フラグを静的 true にしない", not static_publish_true)

# 3. queue worker workflow のトップレベル既定フラグが false
worker = workflows.get("threads-queue-worker.yml", "")
check("threads-queue-worker.yml が存在する", bool(worker))
check("PUBLISH_ENABLED 既定が false", 'PUBLISH_ENABLED: "false"' in worker)
check("ALLOW_REAL_THREADS_POST 既定が false", 'ALLOW_REAL_THREADS_POST: "false"' in worker)
check("ALLOW_REAL_X_POST 既定が false", 'ALLOW_REAL_X_POST: "false"' in worker)
# 既定 dry-run の証拠
check("worker は dry-run 経路を持つ", "--dry-run" in worker)

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
