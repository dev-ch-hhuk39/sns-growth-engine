#!/usr/bin/env python3
"""test_media_approved_pilot_workflow.py — media-approved-pilot.yml の安全性確認。"""
from __future__ import annotations
import sys, os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = FAIL = 0

def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond: PASS += 1; print(f"  [PASS] {label}")
    else:    FAIL += 1; print(f"  [FAIL] {label}")

print("=== test_media_approved_pilot_workflow ===")

wf_path = os.path.join(_ROOT, ".github", "workflows", "media-approved-pilot.yml")
assert os.path.exists(wf_path), f"workflow not found: {wf_path}"
wf = open(wf_path).read()

# 安全フラグ
check('PUBLISH_ENABLED: "false"', 'PUBLISH_ENABLED: "false"' in wf)
check('ALLOW_REAL_X_POST: "false"', 'ALLOW_REAL_X_POST: "false"' in wf)
check('ALLOW_REAL_THREADS_POST: "false"', 'ALLOW_REAL_THREADS_POST: "false"' in wf)
check('ALLOW_CLOUDINARY_UPLOAD: "false"', 'ALLOW_CLOUDINARY_UPLOAD: "false"' in wf)
check('ALLOW_TRANSCRIPTION_API: "false"', 'ALLOW_TRANSCRIPTION_API: "false"' in wf)

# beauty_account ガード
check("beauty_account 実行不可ガードあり", "beauty_account" in wf)

# workflow_dispatch のみ (schedule なし)
check("workflow_dispatch のみ (schedule 実行なし)", "workflow_dispatch" in wf and "cron:" not in wf)

# confirm=yes が必要
check("approved_media_real に confirm=yes ガードあり", "CONFIRM == 'yes'" in wf or "confirm=yes" in wf)
check("confirm なしの SAFETY_STOP あり", "SAFETY_STOP" in wf)

# run: ブロック内に直接 expression 展開なし
import re
run_blocks = re.findall(r'run:\s*\|([^-]+?)(?=\n\s+-|\Z)', wf, re.DOTALL)
direct_expr_in_run = False
for block in run_blocks:
    if re.search(r'\$\{\{[^}]+github\.event\.inputs[^}]+\}\}', block):
        direct_expr_in_run = True
        break
check("run: ブロック内に ${{ github.event.inputs.* }} 直接展開なし", not direct_expr_in_run)

# mode 3段階が存在する
check("plan_only モードあり", "plan_only" in wf)
check("approved_media_dry_run モードあり", "approved_media_dry_run" in wf)
check("approved_media_real モードあり", "approved_media_real" in wf)

print(f"\n結果: PASS={PASS} FAIL={FAIL} / {PASS+FAIL}件")
sys.exit(0 if FAIL == 0 else 1)
