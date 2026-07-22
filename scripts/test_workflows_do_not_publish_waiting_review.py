#!/usr/bin/env python3
"""Scheduled production may publish READY rows, but never WAITING_REVIEW.

Production gates must be scoped to explicit posting steps while workflow-level
defaults remain false. X posting is forbidden in every scheduled workflow.
"""
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

# 2. 定時実行で実投稿を許すのは明示した本番workflowだけ。
production_scheduled = {
    "autonomous-growth-loop-night-scout.yml",
    "autonomous-growth-loop-liver-manager.yml",
    "content-slot-recovery.yml",
}
actual_scheduled_publishers: set[str] = set()
for name, src in workflows.items():
    if "schedule:" not in src:
        continue
    publish_true = 'PUBLISH_ENABLED: "true"' in src or 'ALLOW_REAL_THREADS_POST: "true"' in src
    if publish_true:
        actual_scheduled_publishers.add(name)
        check(f"{name}: 許可済み本番workflow", name in production_scheduled)
        check(f"{name}: workflow既定PUBLISHはfalse", 'PUBLISH_ENABLED: "false"' in src)
        check(f"{name}: workflow既定Threads実投稿はfalse", 'ALLOW_REAL_THREADS_POST: "false"' in src)
        check(f"{name}: X実投稿はfalse固定", 'ALLOW_REAL_X_POST: "false"' in src and 'ALLOW_REAL_X_POST: "true"' not in src)
        first_plan = src.find("--dry-run")
        first_publish = min(
            pos for pos in (src.find('PUBLISH_ENABLED: "true"'), src.find('ALLOW_REAL_THREADS_POST: "true"'))
            if pos >= 0
        )
        check(f"{name}: dry-runがpublish gateより先", 0 <= first_plan < first_publish)
check("scheduled publisher集合が明示allowlistと一致", actual_scheduled_publishers == production_scheduled)

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
